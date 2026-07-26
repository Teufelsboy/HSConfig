import copy
import json
from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.cli import main
from hsconfig.io import read_json, write_json
from hsconfig.runtime_apply import apply_package


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

SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _build_authoritative_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    name: str = "package",
) -> Path:
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    package = tmp_path / name
    code = main(
        [
            "build",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / f"{name}-runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["status"] == "passed"
    return package


def _first_reason_code(gate: dict) -> str:
    reason = gate["reasons"][0]
    return str(reason.get("code") or reason.get("reason"))


def _first_runtime_json(package: Path) -> Path:
    return next(
        path
        for path in sorted((package / "CustomConfig").rglob("*.json"))
        if path.name not in {"GlobalValues.json", "Mulligan.json"}
    )


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


def test_configuration_assurance_does_not_change_apply_gate_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    summary = read_json(package / "reports" / "operator_summary.json")
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


def test_untouched_builder_package_has_verified_derivation_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)

    receipt = read_json(package / "package_derivation_receipt.json")
    summary = read_json(package / "reports" / "operator_summary.json")
    gate = evaluate_apply_gate(package)

    assert receipt["schema_version"] == 1
    assert summary["package_derivation"] == {
        "schema_version": 1,
        "receipt_path": "package_derivation_receipt.json",
        "receipt_sha256": summary["package_derivation"]["receipt_sha256"],
        "verified": True,
    }
    assert summary["package_derivation"]["receipt_sha256"].startswith("sha256:")
    assert gate["allowed"] is True
    assert gate["status"] == "allowed"


def test_forged_valid_operator_summary_cannot_authorize_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    original = read_json(package / "reports" / "operator_summary.json")
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": original["generated_files"],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "operator_summary_derivation_inconsistent"


def test_apply_gate_blocks_runtime_json_value_changed_after_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    runtime_path = _first_runtime_json(package)
    runtime_payload = read_json(runtime_path)
    runtime_payload["ConfigComment"] = "tampered after package build"
    write_json(runtime_path, runtime_payload)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_mismatch"


def test_apply_gate_blocks_runtime_json_added_after_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    deck_dir = next(path for path in (package / "CustomConfig").iterdir() if path.is_dir())
    write_json(
        deck_dir / "ZZZ_999.json",
        {
            "GameCardId": "ZZZ_999",
            "ConfigComment": "tampered after package build",
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_mismatch"


def test_apply_gate_blocks_authoritative_input_changed_after_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    identity_path = package / "reports" / "deck_identity.json"
    identity = read_json(identity_path)
    identity["tampered_after_build"] = True
    write_json(identity_path, identity)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_mismatch"


def test_apply_gate_blocks_missing_derivation_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    (package / "package_derivation_receipt.json").unlink()

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_receipt_missing"


def test_apply_gate_blocks_unknown_derivation_receipt_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hsconfig.package_derivation_receipt import (
        package_derivation_receipt_sha256,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    receipt_path = package / "package_derivation_receipt.json"
    receipt = read_json(receipt_path)
    receipt["schema_version"] = 999
    write_json(receipt_path, receipt)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["package_derivation"]["receipt_sha256"] = (
        package_derivation_receipt_sha256(receipt)
    )
    write_json(summary_path, summary)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_receipt_schema_unsupported"


def test_apply_gate_blocks_derivation_receipt_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    receipt_path = package / "package_derivation_receipt.json"
    receipt = read_json(receipt_path)
    receipt["inputs"] = {}
    write_json(receipt_path, receipt)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_receipt_digest_mismatch"


def test_strict_validation_failure_blocks_even_when_receipt_verifier_is_forced_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    monkeypatch.setattr(
        "hsconfig.apply_gate.validate_complete_package",
        lambda _package: {
            "status": "failed",
            "errors": ["forced strict validation failure"],
        },
        raising=False,
    )
    monkeypatch.setattr(
        "hsconfig.apply_gate.verify_package_derivation_receipt",
        lambda _package, _receipt: (True, []),
        raising=False,
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "strict_package_validation_failed"


def test_same_logical_package_has_identical_derivation_receipt_across_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _build_authoritative_package(
        tmp_path,
        monkeypatch,
        capsys,
        name="first-package",
    )
    second = _build_authoritative_package(
        tmp_path,
        monkeypatch,
        capsys,
        name="second-package",
    )

    first_receipt = read_json(first / "package_derivation_receipt.json")
    second_receipt = read_json(second / "package_derivation_receipt.json")
    first_summary = read_json(first / "reports" / "operator_summary.json")
    second_summary = read_json(second / "reports" / "operator_summary.json")

    assert first_receipt == second_receipt
    assert (
        first_summary["package_derivation"]["receipt_sha256"]
        == second_summary["package_derivation"]["receipt_sha256"]
    )
    serialized = json.dumps(first_receipt, sort_keys=True)
    assert str(first) not in serialized
    assert str(second) not in serialized


def test_derivation_receipt_excludes_volatile_timestamps_and_absolute_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hsconfig.package_derivation_receipt import (
        build_package_derivation_receipt,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    before = build_package_derivation_receipt(package)
    identity_path = package / "reports" / "deck_identity.json"
    identity = read_json(identity_path)
    identity["generated_at"] = "2030-01-15T12:00:00Z"
    identity["opaque_reference"] = str(tmp_path / "private" / "deck.json")
    write_json(identity_path, identity)

    after = build_package_derivation_receipt(package)

    assert after == before


def test_derivation_receipt_is_non_circular(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hsconfig.package_derivation_receipt import (
        build_package_derivation_receipt,
        package_derivation_receipt_sha256,
        verify_package_derivation_receipt,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    receipt_path = package / "package_derivation_receipt.json"
    summary_path = package / "reports" / "operator_summary.json"
    receipt = read_json(receipt_path)
    digest = package_derivation_receipt_sha256(receipt)

    summary = read_json(summary_path)
    summary["non_authoritative_tamper"] = "summary must not hash itself"
    write_json(summary_path, summary)
    write_json(receipt_path, {**receipt, "untrusted_extra": True})

    rebuilt = build_package_derivation_receipt(package)
    verified, reasons = verify_package_derivation_receipt(package, receipt)

    assert rebuilt == receipt
    assert package_derivation_receipt_sha256(rebuilt) == digest
    assert verified is True
    assert reasons == []
    assert "package_derivation_receipt.json" not in receipt["runtime_files"]
    assert "reports/operator_summary.json" not in receipt["inputs"]


def test_runtime_apply_rejects_tamper_before_runtime_write_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    runtime_path = _first_runtime_json(package)
    runtime_payload = read_json(runtime_path)
    runtime_payload["ConfigComment"] = "tampered before runtime apply"
    write_json(runtime_path, runtime_payload)

    def fail_if_runtime_write_boundary_is_reached(**_kwargs):
        raise AssertionError("runtime write boundary must not be reached")

    monkeypatch.setattr(
        "hsconfig.runtime_apply._snapshot_existing_runtime_target",
        fail_if_runtime_write_boundary_is_reached,
    )
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="package_derivation_mismatch"):
        apply_package(package_root=package, runtime_root=runtime)

    assert not runtime.exists()
