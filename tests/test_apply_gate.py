from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json, write_json
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    DERIVATION_RECEIPT_SCHEMA_VERSION,
    build_package_derivation_receipt,
    write_package_derivation_receipt,
)
from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.source_acquisition_provenance import (
    CAPTURED_RECORD,
    FIXTURE_MAP,
    LEGACY_CLAIMS_JSON,
    MANUAL_EVIDENCE,
    build_acquisition_provenance,
)
from tests.helpers.current_globalvalues_contract import (
    GLOBALVALUES_AUTHORITY_MATRIX_PATH,
    write_current_globalvalues_contract,
)
from tests.helpers.current_runtime_surface_ledger_contract import (
    write_current_runtime_surface_ledger,
)


SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _verified_deck_input_fixture() -> tuple[list[dict], dict]:
    cards = decode_deck_code(SHADOWPRIEST_DECK_CODE)["cards"]
    digest = stable_deck_fingerprint(
        (str(card["card_id"]), int(card["count"])) for card in cards
    )
    return cards, {
        "status": "decoded_from_deck_code",
        "runtime_apply_eligible": True,
        "normalized_roster_sha256": f"sha256:{digest}",
    }


def _write_operator_summary(package: Path, payload: dict) -> None:
    operator_path = package / "reports" / "operator_summary.json"
    write_json(operator_path, payload)
    manifest_path = package / "reports" / "input_manifest.json"
    custom_config = package / "CustomConfig"
    if not manifest_path.is_file() or not custom_config.is_dir():
        return

    deck_dirs = sorted(path for path in custom_config.iterdir() if path.is_dir())
    if len(deck_dirs) != 1:
        return
    globalvalues_path = deck_dirs[0] / "GlobalValues.json"
    if not globalvalues_path.is_file():
        return
    globalvalues = read_json(globalvalues_path)
    if not isinstance(globalvalues, dict):
        return
    reports = package / "reports"
    write_current_globalvalues_contract(package, globalvalues)
    manifest = read_json(manifest_path)
    deck_name = str(manifest.get("deck_name", "deck"))
    cards, verification = _verified_deck_input_fixture()
    manifest = {
        **manifest,
        "deck_code": SHADOWPRIEST_DECK_CODE,
        "card_source": "deckstring",
        "deck_input_verification": verification,
    }
    write_json(manifest_path, manifest)
    deck_fingerprint = stable_deck_fingerprint(
        (str(card["card_id"]), int(card["count"])) for card in cards
    )
    write_json(
        reports / "deck_identity.json",
        {
            "deck_name": deck_name,
            "deck_fingerprint": deck_fingerprint,
            "cards": cards,
            "main_deck": cards,
        },
    )
    write_json(
        reports / "deck_fingerprint.json",
        {"deck_fingerprint": deck_fingerprint},
    )
    write_json(
        reports / "guide_claim_bundle.json",
        {"canonical_source_receipts": []},
    )
    if not (reports / "card_behavior_plan_report.json").is_file():
        write_json(reports / "card_behavior_plan_report.json", {"rows": []})
    write_current_runtime_surface_ledger(package)
    generated = payload.get("generated_files", [])
    generated_files = list(generated) if isinstance(generated, list) else []
    ownership = build_output_ownership_manifest(
        [
            *generated_files,
            GLOBALVALUES_AUTHORITY_MATRIX_PATH,
            DERIVATION_RECEIPT_PATH,
            "reports/operator_summary.json",
            "reports/output_ownership_manifest.json",
        ]
    )
    write_json(reports / "output_ownership_manifest.json", ownership)
    receipt = build_package_derivation_receipt(package)
    digest = write_package_derivation_receipt(
        package / DERIVATION_RECEIPT_PATH,
        receipt,
    )
    payload = {
        **payload,
        "deck_input_verification": verification,
        "package_derivation": {
            "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
            "receipt_path": DERIVATION_RECEIPT_PATH,
            "receipt_sha256": digest,
            "verified": True,
        },
    }
    if payload.get("technical_status") == "VALID_PACKAGE":
        payload["apply_policy"] = "ALLOWED_WITH_WARNINGS"
        payload.setdefault("runtime_apply_allowed", True)
        payload.setdefault("runtime_apply_mode", "load_safe_apply")
        payload.setdefault("runtime_apply_reason", "runtime_load_safe_package")
    else:
        payload["apply_policy"] = "BLOCKED"
        payload.setdefault("runtime_apply_allowed", False)
        payload.setdefault("runtime_apply_mode", "blocked")
        payload.setdefault("runtime_apply_reason", "invalid_package")
    write_json(operator_path, payload)


def _write_minimal_runtime_package(package: Path) -> None:
    _cards, verification = _verified_deck_input_fixture()
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "metadata-only fixture"},
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "deck",
            "deck_code": SHADOWPRIEST_DECK_CODE,
            "runtime_root": "unused",
            "card_source": "deckstring",
            "deck_input_verification": verification,
        },
    )


def _refresh_derivation_reference(package: Path) -> None:
    receipt = build_package_derivation_receipt(package)
    digest = write_package_derivation_receipt(
        package / DERIVATION_RECEIPT_PATH,
        receipt,
    )
    operator_path = package / "reports" / "operator_summary.json"
    summary = read_json(operator_path)
    summary["package_derivation"] = {
        "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
        "receipt_path": DERIVATION_RECEIPT_PATH,
        "receipt_sha256": digest,
        "verified": True,
    }
    write_json(operator_path, summary)


def _assert_blocked_with_integrity_and_parity(
    gate: dict,
    expected_primary: dict,
) -> None:
    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == expected_primary
    assert gate["reasons"][-1]["reason"] == (
        "operator_summary_apply_decision_mismatch"
    )


@pytest.mark.parametrize(
    "mode",
    [
        FIXTURE_MAP,
        CAPTURED_RECORD,
        MANUAL_EVIDENCE,
        LEGACY_CLAIMS_JSON,
    ],
)
def test_apply_gate_blocks_receipt_bound_diagnostic_source_provenance(
    tmp_path: Path,
    mode: str,
):
    package = tmp_path / mode
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
        },
    )
    provenance = build_acquisition_provenance(
        mode=mode,
        content=f"{mode} diagnostic source".encode(),
    )
    write_json(
        package / "reports" / "guide_claim_bundle.json",
        {
            "claims": [
                {
                    "claim_id": f"{mode}-claim",
                    "claim_kind": "card_role",
                    "acquisition_provenance": provenance,
                }
            ],
            "source_evidence_index": [
                {
                    "source_ref": "source:1",
                    "acquisition_provenance": provenance,
                }
            ],
            "canonical_source_receipts": [],
        },
    )
    _refresh_derivation_reference(package)

    receipt = read_json(package / DERIVATION_RECEIPT_PATH)
    gate = evaluate_apply_gate(package)

    assert (
        "reports/guide_claim_bundle.json#source_provenance"
        in receipt["inputs"]
    )
    assert gate["allowed"] is False
    assert gate["reasons"][0]["reason"] == (
        "diagnostic_source_not_apply_eligible"
    )


def test_apply_gate_blocks_prebuilt_summary_when_input_verdict_is_missing(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
        },
    )
    manifest_path = package / "reports" / "input_manifest.json"
    manifest = read_json(manifest_path)
    manifest.pop("deck_input_verification")
    write_json(manifest_path, manifest)
    _refresh_derivation_reference(package)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert gate["reasons"][0]["code"] == "deck_input_not_verified"


def test_apply_gate_blocks_prebuilt_summary_when_input_verdict_disagrees(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
        },
    )
    operator_path = package / "reports" / "operator_summary.json"
    summary = read_json(operator_path)
    summary["deck_input_verification"] = {
        **summary["deck_input_verification"],
        "runtime_apply_eligible": False,
    }
    write_json(operator_path, summary)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert gate["reasons"][0]["code"] == "deck_input_not_verified"


def test_apply_gate_recomputes_forged_eligible_verdict_from_deck_identity(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
        },
    )
    identity_path = package / "reports" / "deck_identity.json"
    identity = read_json(identity_path)
    identity["cards"][0]["count"] += 1
    write_json(identity_path, identity)
    _refresh_derivation_reference(package)

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert gate["reasons"][0]["code"] == "deck_input_not_verified"


def test_apply_gate_allows_source_backed_ready_package(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate == {
        "status": "allowed",
        "allowed": True,
        "operator_summary_path": str(package / "reports" / "operator_summary.json"),
        "mode": "load_safe_apply",
        "policy": "ALLOWED_WITH_WARNINGS",
        "reasons": [
            {"reason": "runtime_load_safe_package"},
            {"reason": "exact_source_not_closed", "blocking": False},
        ],
    }


def test_apply_gate_allows_valid_but_not_guide_strong_as_load_safe_apply(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 3}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate == {
        "status": "allowed",
        "allowed": True,
        "operator_summary_path": str(package / "reports" / "operator_summary.json"),
        "mode": "load_safe_apply",
        "policy": "ALLOWED_WITH_WARNINGS",
        "reasons": [
            {"reason": "runtime_load_safe_package"},
            {"reason": "exact_source_not_closed", "blocking": False},
            {"reason": "semantic_strength_incomplete", "blocking": False},
        ],
    }


def test_apply_gate_allows_minimal_load_safe_package_without_cardid_files(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "STATIC_SEMANTICS_USABLE",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "no_cardid_runtime_rows", "count": 30}],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
    assert gate["reasons"][1] == {
        "reason": "exact_source_not_closed",
        "blocking": False,
    }


def test_apply_gate_allows_valid_runtime_surface_gap_as_load_safe_warning(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 2}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
    assert gate["reasons"][1] == {
        "reason": "exact_source_not_closed",
        "blocking": False,
    }


def test_apply_gate_allows_source_informed_apply_ready_without_flag(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": None,
                "source_gap_count": 2,
            },
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 2}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    default_gate = evaluate_apply_gate(package)

    assert default_gate["status"] == "allowed"
    assert default_gate["mode"] == "load_safe_apply"


def test_apply_gate_allows_load_safe_apply_when_source_gap_readiness_is_blocked(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "source_informed_apply_readiness": {
                "status": "blocked",
                "requires_flag": None,
                "source_gap_count": 2,
                "blocking_reasons": ["cards_need_runtime_surface"],
            },
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 2}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"
    assert gate["reasons"][1] == {
        "reason": "exact_source_not_closed",
        "blocking": False,
    }


def test_apply_gate_rejects_forged_runtime_apply_mode_despite_valid_structure(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "normal_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 3}],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert gate["mode"] == "blocked"
    assert gate["reasons"][0]["reason"] == (
        "operator_summary_apply_decision_mismatch"
    )


def test_apply_gate_blocks_invalid_package(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "INVALID_PACKAGE",
            "semantic_status": "NEEDS_MORE_RESEARCH",
            "next_action": "FIX_PACKAGE_BEFORE_APPLY",
            "apply_policy": "BLOCKED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0]["reason"] == (
        "operator_summary_apply_decision_mismatch"
    )


@pytest.mark.parametrize("surface", ["Presume.json", "Concede.json", "CardBehavior.json"])
def test_apply_gate_blocks_normal_path_optional_surfaces(tmp_path: Path, surface: str):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
                f"CustomConfig\\deck\\{surface}",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    _assert_blocked_with_integrity_and_parity(
        gate,
        {
            "reason": "normal_path_optional_surface_present",
            "generated_file": f"CustomConfig\\deck\\{surface}",
        },
    )


@pytest.mark.parametrize("surface", ["Presume.json", "Concede.json", "CardBehavior.json"])
def test_apply_gate_blocks_actual_optional_surface_when_summary_is_stale(
    tmp_path: Path, surface: str
):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    write_json(package / "CustomConfig" / "deck" / surface, {})
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    _assert_blocked_with_integrity_and_parity(
        gate,
        {
            "reason": "normal_path_optional_surface_present",
            "generated_file": str(package / "CustomConfig" / "deck" / surface),
        },
    )


def test_apply_gate_blocks_nested_runtime_files(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    write_json(package / "CustomConfig" / "deck" / "nested" / "Presume.json", {})
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    _assert_blocked_with_integrity_and_parity(
        gate,
        {
            "reason": "nested_runtime_file_present",
            "generated_file": str(package / "CustomConfig" / "deck" / "nested" / "Presume.json"),
        },
    )


def test_apply_gate_blocks_actual_runtime_file_missing_from_summary(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    write_json(
        package / "CustomConfig" / "deck" / "EX1_999.json",
        {"GameCardId": "EX1_999", "ConfigComment": "unreported"},
    )
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    _assert_blocked_with_integrity_and_parity(
        gate,
        {
            "reason": "actual_runtime_file_not_in_operator_summary",
            "generated_file": str(package / "CustomConfig" / "deck" / "EX1_999.json"),
        },
    )


@pytest.mark.parametrize(
    "generated_files",
    [
        [],
        None,
        "CustomConfig\\deck\\GlobalValues.json",
        ["reports\\operator_summary.json"],
    ],
)
def test_apply_gate_blocks_actual_runtime_files_when_summary_runtime_entries_missing(
    tmp_path: Path, generated_files
):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
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
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "fixture"},
    )
    summary = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "next_action": "READY_TO_APPLY_OR_HANDOFF",
        "apply_policy": "ALLOWED",
        "semantic_blockers": [],
    }
    if generated_files is not None:
        summary["generated_files"] = generated_files
    _write_operator_summary(package, summary)

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "required_runtime_file_not_in_operator_summary",
        "generated_file": "CustomConfig/deck/GlobalValues.json",
    }


def test_apply_gate_blocks_unreported_cardid_file_but_allows_absent_cardid_files(
    tmp_path: Path,
):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
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
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "fixture"},
    )
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    _assert_blocked_with_integrity_and_parity(
        gate,
        {
            "reason": "actual_runtime_file_not_in_operator_summary",
            "generated_file": str(package / "CustomConfig" / "deck" / "EX1_001.json"),
        },
    )


def test_apply_gate_blocks_missing_operator_summary(tmp_path: Path):
    gate = evaluate_apply_gate(tmp_path / "package")

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "missing_operator_summary",
            "path": str(tmp_path / "package" / "reports" / "operator_summary.json"),
        }
    ]


def test_apply_gate_blocks_summary_only_ready_package(tmp_path: Path):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "missing_custom_config_directory",
        "path": str(package / "CustomConfig"),
    }


def test_apply_gate_blocks_package_without_input_manifest(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "missing_input_manifest",
        "path": str(package / "reports" / "input_manifest.json"),
    }


def test_apply_gate_ignores_config_usefulness_when_package_is_load_safe(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
            "config_usefulness": {
                "status": "load_safe_but_thin",
                "runtime_permission_impact": "none",
            },
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"][0]["reason"] == "runtime_load_safe_package"


def test_package_io_reads_optional_profile_when_present(tmp_path: Path):
    package = tmp_path / "package"
    write_json(
        package / "reports" / "globalvalues_profile.json",
        {"status": "present", "speed": "fast"},
    )

    assert read_optional_profile(package) == {"status": "present", "speed": "fast"}


def test_package_io_returns_none_when_optional_profile_missing(tmp_path: Path):
    assert read_optional_profile(tmp_path / "package") is None


def test_package_io_requires_globalvalues_baseline(tmp_path: Path):
    with pytest.raises(ValueError, match="Missing GlobalValues baseline report"):
        read_required_baseline(tmp_path / "package")
