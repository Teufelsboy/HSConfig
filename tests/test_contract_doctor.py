import json
from argparse import Namespace
from pathlib import Path

from hsconfig.commands.contract_doctor import (
    contract_doctor_payload,
    run_contract_doctor_command,
)
from hsconfig.contract_doctor import (
    build_contract_doctor_report,
    render_contract_doctor_markdown,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_contract_doctor_summarizes_operator_and_audit_without_gate(tmp_path: Path):
    package = tmp_path / "package"
    reports = package / "reports"
    write_json(
        reports / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_contract_audit_summary": {
                "non_blocking": True,
                "next_report_to_open": "reports/source_contract_audit.json",
                "runtime_lowered_claims": 2,
            },
        },
    )
    write_json(
        reports / "source_contract_audit.json",
        {
            "schema_version": 1,
            "summary": {
                "claims_total": 3,
                "runtime_lowered_claims": 2,
                "suppressed_claims": 1,
                "runtime_evidence_required_claims": 0,
            },
            "claim_lifecycle_rows": [
                {
                    "claim_id": "claim_1",
                    "claim_kind": "mulligan_keep",
                    "policy_lane": "runtime_lowerable",
                    "surface_gate_decision": "allowed",
                    "surface_gate_reason": "runtime_surface_claim",
                    "builder_or_router_decision": "emitted",
                    "runtime_surface": "Mulligan.json",
                    "first_missing_link": "none",
                },
                {
                    "claim_id": "claim_2",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "policy_lane": "runtime_evidence_required",
                    "surface_gate_decision": "rejected",
                    "surface_gate_reason": "runtime_evidence_required",
                    "builder_or_router_decision": "suppressed",
                    "runtime_surface": "none",
                    "first_missing_link": "runtime_evidence_required",
                },
            ],
            "card_rows": {
                "EX1_001": {
                    "name": "Pressure One",
                    "runtime_surfaces": ["Mulligan.json"],
                    "claim_lanes": {"runtime_lowered": 1},
                    "first_missing_link": "none",
                },
                "EX1_002": {
                    "name": "Runtime Missing",
                    "runtime_surfaces": [],
                    "claim_lanes": {"runtime_evidence_required": 1},
                    "first_missing_link": "runtime_evidence",
                },
            },
        },
    )

    report = build_contract_doctor_report(package)

    assert report["status"] == "ok"
    assert report["authority"]["apply_authority"] == "reports/operator_summary.json"
    assert report["authority"]["diagnostic_only"] is True
    assert report["authority"]["runtime_write_performed"] is False
    assert report["operator"]["technical_status"] == "VALID_PACKAGE"
    assert report["claim_lifecycle"]["total"] == 2
    assert report["claim_lifecycle"]["first_missing_links"]["runtime_evidence_required"] == 1
    assert report["claim_lifecycle"]["runtime_surfaces"]["Mulligan.json"] == 1
    assert report["claim_lifecycle"]["rows"][1]["claim_id"] == "claim_2"
    assert report["card_diagnostics"]["total"] == 2
    assert report["card_diagnostics"]["cards_with_missing_links"][0]["card_id"] == "EX1_002"
    assert "apply_allowed" not in json.dumps(report)


def test_contract_doctor_fails_when_operator_summary_is_missing(tmp_path: Path):
    report = build_contract_doctor_report(tmp_path / "missing-package")

    assert report["status"] == "failed"
    assert report["errors"] == ["missing reports/operator_summary.json"]
    assert report["authority"]["apply_authority"] == "reports/operator_summary.json"
    assert report["authority"]["diagnostic_only"] is True


def test_contract_doctor_markdown_states_diagnostic_only(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "operator_summary.json",
        {"technical_status": "VALID_PACKAGE", "semantic_status": "STATIC_SEMANTICS_USABLE"},
    )

    markdown = render_contract_doctor_markdown(build_contract_doctor_report(package))

    assert "Diagnostic only" in markdown
    assert "operator_summary.json remains the only normal apply authority" in markdown


def test_contract_doctor_payload_can_write_markdown_report(tmp_path: Path):
    package = tmp_path / "package"
    out = tmp_path / "doctor.md"
    write_json(
        package / "reports" / "operator_summary.json",
        {"technical_status": "VALID_PACKAGE", "semantic_status": "STATIC_SEMANTICS_USABLE"},
    )

    payload, code = contract_doctor_payload(
        Namespace(package=str(package), out=str(out), json=False)
    )

    assert code == 0
    assert payload["status"] == "ok"
    assert out.is_file()
    assert "Diagnostic only" in out.read_text(encoding="utf-8")


def test_contract_doctor_rejects_runtime_out_path(tmp_path: Path, capsys):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "operator_summary.json",
        {"technical_status": "VALID_PACKAGE", "semantic_status": "STATIC_SEMANTICS_USABLE"},
    )

    out = tmp_path / "CustomConfig" / "shadowpriest" / "Mulligan.json"
    code = run_contract_doctor_command(
        Namespace(package=str(package), out=str(out), json=True)
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "failed"
    assert "contract-doctor --out must be a .md diagnostic report path" in payload["errors"]
    assert not out.exists()

    markdown_out = tmp_path / "CustomConfig" / "shadowpriest" / "doctor.md"
    code = run_contract_doctor_command(
        Namespace(package=str(package), out=str(markdown_out), json=True)
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "failed"
    assert (
        "contract-doctor --out must not target HearthRanger runtime files"
        in payload["errors"]
    )
    assert not markdown_out.exists()


def test_contract_doctor_keeps_darkbishop_boundary_visible(tmp_path: Path):
    package = tmp_path / "shadowpriest"
    write_json(
        package / "reports" / "operator_summary.json",
        {"technical_status": "VALID_PACKAGE", "semantic_status": "SOURCE_BACKED_STRONG"},
    )
    write_json(
        package / "reports" / "source_contract_audit.json",
        {
            "summary": {"claims_total": 1, "runtime_lowered_claims": 1},
            "claim_lifecycle_rows": [
                {
                    "claim_id": "darkbishop_effect",
                    "claim_kind": "hero_power_transform",
                    "policy_lane": "suppressed_or_conditional",
                    "surface_gate_decision": "allowed",
                    "surface_gate_reason": "cardid_behavior_surface",
                    "builder_or_router_decision": "emitted",
                    "runtime_surface": "SW_448.json",
                    "first_missing_link": "none",
                }
            ],
            "card_rows": {
                "SW_448": {
                    "runtime_surfaces": ["SW_448.json"],
                    "claim_lanes": {"runtime_lowered": 1},
                    "first_missing_link": "none",
                }
            },
        },
    )

    report = build_contract_doctor_report(package)

    assert report["claim_lifecycle"]["runtime_surfaces"]["SW_448.json"] == 1
    assert "Mulligan.json" not in report["claim_lifecycle"]["runtime_surfaces"]
    assert report["card_diagnostics"]["rows"][0]["runtime_surfaces"] == ["SW_448.json"]
    assert report["authority"]["diagnostic_only"] is True


def test_contract_doctor_exposes_spine_summary_without_apply_policy(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
        },
    )

    report = build_contract_doctor_report(package)

    assert report["contract_spine"]["operator_gate_impact"] == "diagnostic_only"
    assert report["contract_spine"]["claim_kind_count"] >= 1
    assert "mulligan_keep" in report["contract_spine"]["claim_kinds"]
    assert "hero_power_transform" in report["contract_spine"]["claim_kinds"]
    assert report["contract_spine"]["unexpected_contract_drift_count"] == 0
    assert report["authority"]["apply_authority"] == "reports/operator_summary.json"

    serialized = json.dumps(report)
    assert '"apply_allowed"' not in serialized
    assert '"runtime_apply_allowed"' not in serialized
    assert '"runtime_apply_mode"' not in serialized
