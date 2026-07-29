import copy
import json
from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.cli import main
from hsconfig.io import read_json, write_json
from hsconfig.runtime_apply import apply_package
from tests.helpers.current_apply_eligible_package import (
    write_current_apply_eligible_package,
    write_current_pre_run_contract,
)
from tests.helpers.current_runtime_surface_ledger_contract import (
    write_current_runtime_surface_ledger,
)


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
    "pre_run_closure",
]

RECEIPT_TAMPERING_CASES = [
    ("unknown_claim_id", "source_receipt_claim_missing"),
    ("claim_signature_mismatch", "source_receipt_signature_mismatch"),
    ("deck_fingerprint_mismatch", "source_receipt_deck_mismatch"),
    ("duplicate_claim_receipt", "source_receipt_duplicate"),
    ("claim_receipt_parity_mismatch", "source_receipt_claim_parity_mismatch"),
    (
        "source_evidence_provenance_mismatch",
        "source_receipt_claim_parity_mismatch",
    ),
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
    "from hsconfig.pre_run_metrics",
    "import hsconfig.pre_run_metrics",
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
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["status"] == "passed"
    return package


def _install_linked_owner_authority(package: Path) -> None:
    from hsconfig.package_derivation_receipt import (
        refresh_package_derivation_authority,
    )

    deck_dir = next(
        path for path in (package / "CustomConfig").iterdir() if path.is_dir()
    )
    owner_path = deck_dir / "EX1_625t.json"
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )
    write_json(
        owner_path,
        {
            "GameCardId": "EX1_625t",
            "ConfigComment": "curated linked runtime owner",
            "BeforeUseHeroPowerBonus": {
                "values": [{"condition": "*", "value": "10"}]
            },
        },
    )
    write_current_runtime_surface_ledger(package)
    write_current_pre_run_contract(package)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    generated_path = owner_path.relative_to(package).as_posix()
    if generated_path not in summary["generated_files"]:
        summary["generated_files"].append(generated_path)
    summary["package_derivation"] = refresh_package_derivation_authority(package)
    write_json(summary_path, summary)


def _remove_linked_owner_authority(package: Path) -> None:
    from hsconfig.package_derivation_receipt import (
        refresh_package_derivation_authority,
    )

    for owner_path in (package / "CustomConfig").glob("*/EX1_625t.json"):
        owner_path.unlink()
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {"rows": []},
    )
    write_current_runtime_surface_ledger(package)
    write_current_pre_run_contract(package)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["generated_files"] = [
        path
        for path in summary["generated_files"]
        if not str(path).replace("\\", "/").endswith("/EX1_625t.json")
    ]
    summary["package_derivation"] = refresh_package_derivation_authority(
        package
    )
    write_json(summary_path, summary)


def _first_reason_code(gate: dict) -> str:
    reason = gate["reasons"][0]
    return str(reason.get("code") or reason.get("reason"))


def _stub_configure_card_fetches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )


def test_configure_operator_and_apply_gate_share_one_literal_decision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_configure_card_fetches(monkeypatch)
    out = tmp_path / "configure"

    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )
    configure = json.loads(capsys.readouterr().out)
    package = out / "04_package"
    operator = read_json(package / "reports" / "operator_summary.json")
    gate = evaluate_apply_gate(package)

    assert code == 0
    assert configure["apply_decision"] == {
        "allowed": True,
        "mode": "load_safe_apply",
        "policy": "ALLOWED_WITH_WARNINGS",
        "reasons": [
            {"reason": "runtime_load_safe_package"},
            {"reason": "exact_source_not_closed", "blocking": False},
            {"reason": "semantic_strength_incomplete", "blocking": False},
        ],
    }
    assert operator["runtime_apply_allowed"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert operator["runtime_apply_reason"] == "runtime_load_safe_package"
    assert operator["exact_source_closed"] is False
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["policy"] == "ALLOWED_WITH_WARNINGS"
    assert gate["reasons"] == configure["apply_decision"]["reasons"]


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("runtime_apply_allowed", False),
        ("runtime_apply_mode", "blocked"),
        ("technical_status", "INVALID_PACKAGE"),
        ("apply_policy", "BLOCKED"),
    ],
)
def test_apply_gate_rejects_serialized_core_field_forgery(
    tmp_path: Path,
    field: str,
    forged_value: object,
) -> None:
    package = write_current_apply_eligible_package(
        tmp_path / "package",
        operator_summary={
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_reason": "runtime_load_safe_package",
        },
    )
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary[field] = forged_value
    write_json(summary_path, summary)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert gate["mode"] == "blocked"
    assert _first_reason_code(gate) == "operator_summary_apply_decision_mismatch"


def test_blocked_apply_decision_audits_stale_allowed_core_fields(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "package")
    next((package / "CustomConfig").glob("*/Mulligan.json")).unlink()

    gate = evaluate_apply_gate(package)
    reason_codes = [
        str(reason.get("code") or reason.get("reason"))
        for reason in gate["reasons"]
    ]

    assert gate["allowed"] is False
    assert gate["mode"] == "blocked"
    assert reason_codes[0] == "missing_required_runtime_file"
    assert reason_codes[-1] == "operator_summary_apply_decision_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    RECEIPT_TAMPERING_CASES,
)
def test_apply_gate_rejects_semantically_tampered_canonical_receipt(
    tmp_path: Path,
    mutation: str,
    expected_reason: str,
) -> None:
    from hsconfig.package_derivation_receipt import (
        refresh_package_derivation_authority,
    )

    package = write_current_apply_eligible_package(tmp_path / mutation)
    bundle_path = package / "reports" / "guide_claim_bundle.json"
    bundle = read_json(bundle_path)
    receipt = bundle["canonical_source_receipts"][0]

    if mutation == "unknown_claim_id":
        receipt["claim_id"] = "claim_missing_from_bundle"
    elif mutation == "claim_signature_mismatch":
        receipt["claim_signature"] = "sha256:" + ("0" * 64)
    elif mutation == "deck_fingerprint_mismatch":
        receipt["matched_deck_fingerprint"] = "sha256:" + ("1" * 64)
    elif mutation == "duplicate_claim_receipt":
        bundle["canonical_source_receipts"].append(copy.deepcopy(receipt))
    elif mutation == "claim_receipt_parity_mismatch":
        receipt["source_url"] = "https://example.test/different-source"
    elif mutation == "source_evidence_provenance_mismatch":
        evidence = bundle["source_evidence_index"][0]
        evidence["acquisition_provenance"]["content_sha256"] = (
            "sha256:" + ("2" * 64)
        )
    else:
        raise AssertionError(f"unknown mutation: {mutation}")

    write_json(bundle_path, bundle)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["package_derivation"] = refresh_package_derivation_authority(
        package
    )
    write_json(summary_path, summary)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == expected_reason


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


def test_apply_gate_reports_operator_summary_as_single_human_authority(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(
        tmp_path / "package",
        operator_summary={
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_reason": "runtime_load_safe_package",
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is True
    assert Path(gate["operator_summary_path"]).resolve() == (
        package / "reports" / "operator_summary.json"
    ).resolve()


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
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["runtime_apply_allowed"] is False
    assert summary["source_apply_eligible"] is False
    assert summary["source_apply_eligibility_reasons"] == [
        "diagnostic_source_not_apply_eligible"
    ]
    assert summary["source_status_apply_blocking"] is False
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

    assert receipt["schema_version"] == 2
    assert receipt["linked_runtime_owners"] == [
        {
            "source_card_id": "SW_448",
            "runtime_card_id": "EX1_625t",
            "link_kind": "hero_power_transform",
            "semantic_surface": "hero_power_before_use",
            "behavior_block": "BeforeUseHeroPowerBonus",
        }
    ]
    assert summary["package_derivation"] == {
        "schema_version": 2,
        "receipt_path": "package_derivation_receipt.json",
        "receipt_sha256": summary["package_derivation"]["receipt_sha256"],
        "verified": True,
    }
    assert summary["package_derivation"]["receipt_sha256"].startswith("sha256:")
    assert gate["allowed"] is True
    assert gate["status"] == "allowed"


def test_derivation_receipt_binds_only_linked_owner_authority_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hsconfig.package_derivation_receipt import (
        build_package_derivation_receipt,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    _install_linked_owner_authority(package)
    before = build_package_derivation_receipt(package)
    plan_path = package / "reports" / "card_behavior_plan_report.json"
    plan = read_json(plan_path)

    assert before["linked_runtime_owners"] == [
        {
            "source_card_id": "SW_448",
            "runtime_card_id": "EX1_625t",
            "link_kind": "hero_power_transform",
            "semantic_surface": "hero_power_before_use",
            "behavior_block": "BeforeUseHeroPowerBonus",
        }
    ]

    plan["generated_at"] = "2099-01-01T00:00:00Z"
    plan["diagnostic_prose"] = "changed prose"
    plan["rows"][0]["claim_id"] = "renamed_non_authority_claim"
    plan["rows"][0]["diagnostic_prose"] = "changed row prose"
    write_json(plan_path, plan)
    after_diagnostics = build_package_derivation_receipt(package)

    plan["rows"][0]["runtime_card_id"] = "SW_448"
    write_json(plan_path, plan)
    after_authority = build_package_derivation_receipt(package)

    assert after_diagnostics == before
    assert after_authority != before


@pytest.mark.parametrize(
    "mutation",
    [
        "remove",
        "invalid_json",
        "non_object",
        "empty_rows",
        "invalid_rows_container",
    ],
)
def test_apply_gate_fails_closed_without_valid_linked_owner_plan_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    _install_linked_owner_authority(package)
    assert evaluate_apply_gate(package)["allowed"] is True
    path = package / "reports" / "card_behavior_plan_report.json"
    if mutation == "remove":
        path.unlink()
    elif mutation == "invalid_json":
        path.write_text("{", encoding="utf-8")
    elif mutation == "non_object":
        path.write_text("[]", encoding="utf-8")
    elif mutation == "empty_rows":
        write_json(path, {"rows": []})
    else:
        write_json(path, {"rows": {}})
    if mutation == "empty_rows":
        from hsconfig.package_derivation_receipt import (
            refresh_package_derivation_authority,
        )

        summary_path = package / "reports" / "operator_summary.json"
        summary = read_json(summary_path)
        summary["package_derivation"] = refresh_package_derivation_authority(
            package
        )
        write_json(summary_path, summary)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) in {
        "linked_runtime_owner_evidence_missing",
        "linked_runtime_owner_evidence_invalid",
    }


def test_apply_gate_rejects_legacy_derivation_receipt_schema_one(
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
    receipt["schema_version"] = 1
    receipt.pop("linked_runtime_owners", None)
    write_json(receipt_path, receipt)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["package_derivation"]["schema_version"] = 1
    summary["package_derivation"]["receipt_sha256"] = (
        package_derivation_receipt_sha256(receipt)
    )
    write_json(summary_path, summary)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_receipt_schema_unsupported"


@pytest.mark.parametrize(
    "rows",
    [{}, None, "corrupt", [None]],
    ids=["object", "null", "string", "non_object_row"],
)
def test_ownerless_invalid_behavior_plan_rows_cannot_build_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rows: object,
) -> None:
    from hsconfig.package_derivation_receipt import (
        build_package_derivation_receipt,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    _remove_linked_owner_authority(package)
    assert evaluate_apply_gate(package)["allowed"] is True
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {"rows": rows},
    )

    with pytest.raises(
        ValueError,
        match="^linked_runtime_owner_evidence_invalid$",
    ):
        build_package_derivation_receipt(package)


@pytest.mark.parametrize(
    "rows",
    [{}, None, "corrupt", [None]],
    ids=["object", "null", "string", "non_object_row"],
)
def test_apply_gate_rejects_ownerless_invalid_behavior_plan_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rows: object,
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    _remove_linked_owner_authority(package)
    assert evaluate_apply_gate(package)["allowed"] is True
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {"rows": rows},
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "linked_runtime_owner_evidence_invalid"


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
            "deck_input_verification": original["deck_input_verification"],
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


def test_apply_gate_rejects_boolean_summary_schema_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["package_derivation"]["schema_version"] = True
    write_json(summary_path, summary)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "operator_summary_derivation_inconsistent"


@pytest.mark.parametrize("schema_version", [True, 1.0])
def test_receipt_verifier_and_apply_gate_reject_non_integer_schema_versions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    schema_version: object,
) -> None:
    from hsconfig.package_derivation_receipt import (
        package_derivation_receipt_sha256,
        verify_package_derivation_receipt,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    receipt_path = package / "package_derivation_receipt.json"
    receipt = read_json(receipt_path)
    receipt["schema_version"] = schema_version
    write_json(receipt_path, receipt)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["package_derivation"]["schema_version"] = schema_version
    summary["package_derivation"]["receipt_sha256"] = (
        package_derivation_receipt_sha256(receipt)
    )
    write_json(summary_path, summary)

    verified, reasons = verify_package_derivation_receipt(package, receipt)
    gate = evaluate_apply_gate(package)

    assert verified is False
    assert reasons[0]["code"] == "package_derivation_receipt_schema_unsupported"
    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_receipt_schema_unsupported"


def test_apply_gate_rejects_integer_verified_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["package_derivation"]["verified"] = 1
    write_json(summary_path, summary)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "operator_summary_derivation_inconsistent"


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
    write_json(identity_path, identity)
    manifest_path = package / "reports" / "input_manifest.json"
    manifest = read_json(manifest_path)
    manifest["runtime_root"] = str(tmp_path / "different-runtime-root")
    write_json(manifest_path, manifest)

    after = build_package_derivation_receipt(package)

    assert after == before


def test_path_like_deck_identity_is_semantic_and_mutation_evident(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hsconfig.package_derivation_receipt import (
        build_package_derivation_receipt,
        refresh_package_derivation_authority,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    identity_path = package / "reports" / "deck_identity.json"
    identity = read_json(identity_path)
    identity["deck_name"] = "/Alpha"
    write_json(identity_path, identity)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["package_derivation"] = refresh_package_derivation_authority(package)
    write_json(summary_path, summary)
    before = build_package_derivation_receipt(package)

    identity["deck_name"] = "/Beta"
    write_json(identity_path, identity)
    after = build_package_derivation_receipt(package)
    gate = evaluate_apply_gate(package)

    assert after != before
    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "package_derivation_mismatch"


@pytest.mark.parametrize(
    ("mutation", "expected_gate_code"),
    [
        ("negative_deck_eligibility", "deck_input_not_verified"),
        ("invalid_source_authority", "source_authority_receipt_invalid"),
        ("receipt_mismatch", "package_derivation_mismatch"),
    ],
)
def test_builder_summary_never_claims_valid_when_task4_authority_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
    expected_gate_code: str,
) -> None:
    from hsconfig import package_builder

    original_refresh = package_builder.refresh_package_derivation_authority

    def refresh_with_authority_mutation(package_root: Path) -> dict:
        package = Path(package_root)
        if mutation == "negative_deck_eligibility":
            write_json(
                package / "reports" / "deck_input_verification.json",
                {"runtime_apply_eligible": False},
            )
        elif mutation == "invalid_source_authority":
            bundle_path = package / "reports" / "guide_claim_bundle.json"
            bundle = read_json(bundle_path)
            bundle["canonical_source_receipts"] = [
                {
                    "receipt_kind": "canonical_exact_deck_source_document",
                    "acquisition_provenance": {
                        "mode": "manual_evidence",
                        "content_sha256": "sha256:" + ("0" * 64),
                        "authority": "manual_unverified",
                    },
                }
            ]
            write_json(bundle_path, bundle)
        authority = original_refresh(package)
        if mutation == "receipt_mismatch":
            identity_path = package / "reports" / "deck_identity.json"
            identity = read_json(identity_path)
            identity["tampered_after_receipt"] = True
            write_json(identity_path, identity)
        return authority

    monkeypatch.setattr(
        package_builder,
        "refresh_package_derivation_authority",
        refresh_with_authority_mutation,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    summary = read_json(package / "reports" / "operator_summary.json")
    gate = evaluate_apply_gate(package)

    assert summary["technical_status"] == "INVALID_PACKAGE"
    assert gate["allowed"] is False
    assert _first_reason_code(gate) == expected_gate_code


def test_builder_summary_recomputes_strict_validation_after_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hsconfig import package_builder

    original_refresh = package_builder.refresh_package_derivation_authority

    def refresh_then_add_unowned_linked_runtime(package_root: Path) -> dict:
        package = Path(package_root)
        authority = original_refresh(package)
        plan_path = package / "reports" / "card_behavior_plan_report.json"
        plan = read_json(plan_path)
        plan["rows"].append(
            {
                "claim_id": "post_receipt_strict_mutation",
                "card_id": "SW_448",
                "source_card_id": "SW_448",
                "runtime_card_id": "MISSING_RUNTIME_OWNER",
                "link_kind": "hero_power_transform",
                "behavior_block": "BeforeUseHeroPowerBonus",
                "meaningful_runtime_surface": True,
            }
        )
        write_json(plan_path, plan)
        return authority

    monkeypatch.setattr(
        package_builder,
        "refresh_package_derivation_authority",
        refresh_then_add_unowned_linked_runtime,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    summary = read_json(package / "reports" / "operator_summary.json")
    gate = evaluate_apply_gate(package)

    assert summary["technical_status"] == "INVALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is False
    assert gate["allowed"] is False
    assert _first_reason_code(gate) == "strict_package_validation_failed"


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


def test_runtime_apply_rejects_missing_deck_input_verdict_before_destination_prep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from hsconfig.package_derivation_receipt import (
        refresh_package_derivation_authority,
    )

    package = _build_authoritative_package(tmp_path, monkeypatch, capsys)
    manifest_path = package / "reports" / "input_manifest.json"
    manifest = read_json(manifest_path)
    manifest.pop("deck_input_verification", None)
    write_json(manifest_path, manifest)
    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary.pop("deck_input_verification", None)
    summary["package_derivation"] = refresh_package_derivation_authority(package)
    write_json(summary_path, summary)

    def fail_if_destination_prep_is_reached(*_args, **_kwargs):
        raise AssertionError("runtime destination preparation must not be reached")

    monkeypatch.setattr(
        "hsconfig.runtime_apply._single_config_dir",
        fail_if_destination_prep_is_reached,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_apply._snapshot_existing_runtime_target",
        fail_if_destination_prep_is_reached,
    )
    runtime = tmp_path / "runtime"

    with pytest.raises(ValueError, match="deck_input_not_verified"):
        apply_package(package_root=package, runtime_root=runtime)

    assert not runtime.exists()
