from pathlib import Path
from copy import deepcopy

import pytest

import hsconfig.apply_gate as apply_gate_module
from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.io import read_json, write_json
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import load_operator_summary_inputs
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    DERIVATION_RECEIPT_SCHEMA_VERSION,
    OPTIMIZED_DERIVATION_RECEIPT_SCHEMA_VERSION,
    build_package_derivation_receipt,
    build_package_authority_context,
    refresh_package_derivation_authority,
    write_package_derivation_receipt,
)
from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.package_model import DirectoryPackageView
from hsconfig.package_render_authority import render_package_authority
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
from tests.helpers.current_apply_eligible_package import (
    write_current_pre_run_contract,
)
from tests.helpers.current_runtime_surface_ledger_contract import (
    write_current_runtime_surface_ledger,
)
from tests.test_package_render_authority import _optimized_model


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
    write_current_pre_run_contract(package)
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


def _write_valid_optimized_package(
    package: Path,
    *,
    model_root: Path,
) -> Path:
    rendered = render_package_authority(_optimized_model(model_root))
    for artifact in rendered.artifacts.artifacts:
        target = package / artifact.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content)
    return package


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


def test_apply_gate_allows_valid_llm_optimized_start(tmp_path: Path):
    package = _write_valid_optimized_package(
        tmp_path / "optimized",
        model_root=tmp_path / "model",
    )
    summary = read_json(package / "reports" / "operator_summary.json")
    decision = read_json(
        package
        / "reports"
        / "optimized_start"
        / "starter_config_decision.json"
    )
    selected = read_json(
        package
        / "reports"
        / "optimized_start"
        / f"{decision['selected_candidate_id']}.json"
    )

    assert summary["package_derivation"]["selected_candidate_sha256"] == (
        selected["content_sha256"]
    )
    assert summary["package_derivation"]["decision_sha256"] == (
        decision["content_sha256"]
    )
    assert refresh_package_derivation_authority(package) == (
        summary["package_derivation"]
    )
    assert build_package_authority_context(package)[
        "optimized_start_derivation_validity"
    ] is True

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["policy"] == "ALLOWED_WITH_WARNINGS"
    assert gate["reasons"] == [
        {"reason": "runtime_load_safe_package"},
        {"reason": "exact_source_not_closed", "blocking": False},
        {"reason": "semantic_strength_incomplete", "blocking": False},
        {
            "reason": "diagnostic_source_not_apply_eligible",
            "code": "diagnostic_source_not_apply_eligible",
            "detail": (
                "Package source provenance is diagnostic-only and cannot "
                "authorize runtime apply."
            ),
            "blocking": False,
        },
    ]


def test_apply_gate_rejects_optimized_summary_digest_mismatch(
    tmp_path: Path,
) -> None:
    package = _write_valid_optimized_package(
        tmp_path / "optimized",
        model_root=tmp_path / "model",
    )
    summary_path = package / "reports" / "operator_summary.json"
    original_summary = read_json(summary_path)
    invalid_digest = "sha256:" + "0" * 64

    for field in ("selected_candidate_sha256", "decision_sha256"):
        for replacement in (None, invalid_digest):
            tampered_summary = deepcopy(original_summary)
            if replacement is None:
                tampered_summary["package_derivation"].pop(field, None)
            else:
                tampered_summary["package_derivation"][field] = replacement
            write_json(summary_path, tampered_summary)

            gate = evaluate_apply_gate(package)

            assert gate["allowed"] is False
            assert gate["reasons"][0]["reason"] == (
                "operator_summary_derivation_inconsistent"
            )

    write_json(summary_path, original_summary)
    decision = read_json(
        package
        / "reports"
        / "optimized_start"
        / "starter_config_decision.json"
    )
    selected_path = (
        package
        / "reports"
        / "optimized_start"
        / f"{decision['selected_candidate_id']}.json"
    )
    invalid_selected = read_json(selected_path)
    invalid_selected["unexpected"] = True
    write_json(selected_path, invalid_selected)
    receipt_path = package / DERIVATION_RECEIPT_PATH
    valid_receipt_bytes = receipt_path.read_bytes()
    with pytest.raises(
        ValueError,
        match="^optimized_start_derivation_invalid$",
    ):
        refresh_package_derivation_authority(package)
    assert receipt_path.read_bytes() == valid_receipt_bytes
    refreshed_receipt = build_package_derivation_receipt(package)
    refreshed_receipt_sha256 = write_package_derivation_receipt(
        receipt_path,
        refreshed_receipt,
    )
    invalid_summary = deepcopy(original_summary)
    invalid_summary["package_derivation"]["receipt_sha256"] = (
        refreshed_receipt_sha256
    )
    write_json(summary_path, invalid_summary)
    assert build_package_authority_context(package)[
        "optimized_start_derivation_validity"
    ] is False

    gate = evaluate_apply_gate(package)

    assert gate["allowed"] is False
    assert gate["reasons"][0]["reason"] == (
        "optimized_start_derivation_invalid"
    )


def test_optimized_derivation_rejects_swapped_candidate_files(
    tmp_path: Path,
) -> None:
    package = _write_valid_optimized_package(
        tmp_path / "optimized",
        model_root=tmp_path / "model",
    )
    optimized = package / "reports" / "optimized_start"
    candidate_1 = optimized / "candidate-1.json"
    candidate_2 = optimized / "candidate-2.json"
    candidate_1_bytes = candidate_1.read_bytes()
    candidate_2_bytes = candidate_2.read_bytes()
    candidate_1.write_bytes(candidate_2_bytes)
    candidate_2.write_bytes(candidate_1_bytes)

    refresh_error = None
    try:
        refreshed = refresh_package_derivation_authority(package)
    except ValueError as error:
        refresh_error = str(error)
    else:
        summary_path = package / "reports" / "operator_summary.json"
        summary = read_json(summary_path)
        summary["package_derivation"] = refreshed
        write_json(summary_path, summary)

    replay_error = None
    try:
        inputs = load_operator_summary_inputs(DirectoryPackageView(package))
        replayed = build_operator_summary_from_inputs(inputs)
        write_json(package / "reports" / "operator_summary.json", replayed)
    except ValueError as error:
        replay_error = str(error)

    gate = evaluate_apply_gate(package)

    assert (
        refresh_error,
        replay_error,
        gate["allowed"],
        gate["reasons"][0]["reason"],
    ) == (
        "optimized_start_derivation_invalid",
        "optimized_start_derivation_invalid",
        False,
        "optimized_start_derivation_invalid",
    )


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


@pytest.mark.parametrize(
    ("content", "reason"),
    ((b"{", "invalid_operator_summary_json"), (b"[]\n", "invalid_operator_summary")),
)
def test_apply_gate_rejects_invalid_operator_summary_document(
    tmp_path: Path,
    content: bytes,
    reason: str,
) -> None:
    operator = tmp_path / "reports" / "operator_summary.json"
    operator.parent.mkdir()
    operator.write_bytes(content)

    gate = evaluate_apply_gate(tmp_path)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0]["reason"] == reason


def test_recompute_without_summary_core_enforcement_returns_recomputed_facts(
    tmp_path: Path,
) -> None:
    decision, facts = apply_gate_module.recompute_apply_decision(
        tmp_path,
        {},
        enforce_summary_core_fields=False,
    )

    assert decision.allowed is False
    assert decision.reasons[0]["reason"] == "missing_custom_config_directory"
    assert facts.actual_runtime_surface_inventory is False
    assert facts.package_summary_parity is True


def test_recompute_blocks_when_manifest_disappears_after_structure_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
        },
    )
    summary = read_json(package / "reports" / "operator_summary.json")
    manifest_path = package / "reports" / "input_manifest.json"
    real_read_json = apply_gate_module.read_json
    manifest_read_failed = False

    def _manifest_disappears_once(path: str | Path) -> object:
        nonlocal manifest_read_failed
        if Path(path) == manifest_path and not manifest_read_failed:
            manifest_read_failed = True
            raise FileNotFoundError(str(path))
        return real_read_json(path)

    monkeypatch.setattr(apply_gate_module, "read_json", _manifest_disappears_once)

    decision, _facts = apply_gate_module.recompute_apply_decision(
        package,
        summary,
        enforce_summary_core_fields=True,
    )

    assert manifest_read_failed is True
    assert decision.allowed is False
    assert decision.reasons[0]["reason"] == "configuration_mode_invalid"


def test_deck_input_reasons_preserve_existing_authority_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = [{"reason": "deck_input_receipt_stale", "code": "stale"}]
    monkeypatch.setattr(
        apply_gate_module,
        "deck_input_apply_eligibility_reasons",
        lambda _package: existing,
    )

    assert apply_gate_module._deck_input_verification_reasons(tmp_path, {}) is existing


@pytest.mark.parametrize(
    ("manifest", "identity", "detail"),
    (
        ([], {}, "deck input authority documents must be objects"),
        ({}, {"cards": {}}, "deck identity cards must be a list"),
    ),
)
def test_deck_input_reasons_reject_invalid_authority_document_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest: object,
    identity: object,
    detail: str,
) -> None:
    reports = tmp_path / "reports"
    write_json(reports / "input_manifest.json", manifest)
    write_json(reports / "deck_identity.json", identity)
    monkeypatch.setattr(
        apply_gate_module,
        "deck_input_apply_eligibility_reasons",
        lambda _package: [],
    )

    reasons = apply_gate_module._deck_input_verification_reasons(tmp_path, {})

    assert reasons == [
        {
            "reason": "deck_input_not_verified",
            "code": "deck_input_not_verified",
            "detail": detail,
        }
    ]


def test_strict_validation_surfaces_linked_owner_error_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    linked_code = apply_gate_module.LINKED_RUNTIME_OWNER_EVIDENCE_MISSING
    monkeypatch.setattr(
        apply_gate_module,
        "validate_complete_package",
        lambda _package: {"status": "failed", "errors": [linked_code]},
    )
    monkeypatch.setattr(
        apply_gate_module,
        "strict_validation_passed",
        lambda _report: False,
    )

    assert apply_gate_module._strict_package_validation_reasons(tmp_path) == [
        {
            "reason": linked_code,
            "code": linked_code,
            "detail": "Linked runtime owner evidence is unavailable or invalid.",
            "errors": [linked_code],
        }
    ]


def _write_derivation_payload(package: Path, payload: object) -> Path:
    receipt = package / DERIVATION_RECEIPT_PATH
    write_json(receipt, payload)
    return receipt


def test_derivation_reasons_require_summary_metadata_when_receipt_exists(
    tmp_path: Path,
) -> None:
    _write_derivation_payload(tmp_path, {"schema_version": 1})

    reasons = apply_gate_module._package_derivation_reasons(tmp_path, {})

    assert reasons[0]["reason"] == "operator_summary_derivation_inconsistent"


@pytest.mark.parametrize(
    ("raw", "expected_detail"),
    (
        (b"{", "Package derivation receipt is not valid JSON."),
        (b"[]\n", "Package derivation receipt must be an object."),
    ),
)
def test_derivation_reasons_reject_invalid_receipt_document(
    tmp_path: Path,
    raw: bytes,
    expected_detail: str,
) -> None:
    receipt = tmp_path / DERIVATION_RECEIPT_PATH
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_bytes(raw)

    reasons = apply_gate_module._package_derivation_reasons(
        tmp_path,
        {"package_derivation": {}},
    )

    assert reasons[0]["reason"] == "package_derivation_receipt_digest_mismatch"
    assert reasons[0]["detail"] == expected_detail


def test_derivation_reasons_reject_unsupported_receipt_schema(tmp_path: Path) -> None:
    _write_derivation_payload(tmp_path, {"schema_version": 999})

    reasons = apply_gate_module._package_derivation_reasons(
        tmp_path,
        {"package_derivation": {}},
    )

    assert reasons[0]["reason"] == "package_derivation_receipt_schema_unsupported"


@pytest.mark.parametrize(
    ("strategy_authority_mode", "receipt_schema_version", "expected_reason"),
    (
        (
            "source_contract",
            OPTIMIZED_DERIVATION_RECEIPT_SCHEMA_VERSION,
            "package_derivation_receipt_schema_unsupported",
        ),
        (
            "llm_optimized_start",
            DERIVATION_RECEIPT_SCHEMA_VERSION,
            "optimized_start_derivation_invalid",
        ),
    ),
)
def test_derivation_reasons_reject_supported_schema_from_other_authority_mode(
    tmp_path: Path,
    strategy_authority_mode: str,
    receipt_schema_version: int,
    expected_reason: str,
) -> None:
    _write_derivation_payload(
        tmp_path,
        {"schema_version": receipt_schema_version},
    )

    reasons = apply_gate_module._package_derivation_reasons(
        tmp_path,
        {"package_derivation": {}},
        strategy_authority_mode=strategy_authority_mode,
    )

    assert reasons[0]["reason"] == expected_reason


def test_derivation_reasons_reject_inconsistent_summary_schema(
    tmp_path: Path,
) -> None:
    _write_derivation_payload(
        tmp_path,
        {"schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION},
    )

    reasons = apply_gate_module._package_derivation_reasons(
        tmp_path,
        {"package_derivation": {"schema_version": 999, "verified": True}},
    )

    assert reasons[0]["reason"] == "operator_summary_derivation_inconsistent"


def _patch_derivation_verifiers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    verified: bool,
    verification_reasons: list[dict] | None = None,
) -> None:
    monkeypatch.setattr(
        apply_gate_module,
        "derivation_schema_version_supported",
        lambda _version: True,
    )
    monkeypatch.setattr(
        apply_gate_module,
        "package_derivation_receipt_sha256",
        lambda _receipt: "digest",
    )
    monkeypatch.setattr(
        apply_gate_module,
        "verify_package_derivation_receipt",
        lambda _package, _receipt: (verified, verification_reasons or []),
    )


def _summary_derivation(**overrides: object) -> dict[str, object]:
    summary = {
        "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
        "receipt_path": DERIVATION_RECEIPT_PATH,
        "receipt_sha256": "digest",
        "verified": True,
    }
    summary.update(overrides)
    return {"package_derivation": summary}


def test_derivation_reasons_reject_summary_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_derivation_payload(
        tmp_path,
        {"schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION},
    )
    _patch_derivation_verifiers(monkeypatch, verified=True)

    reasons = apply_gate_module._package_derivation_reasons(
        tmp_path,
        _summary_derivation(receipt_sha256="wrong"),
    )

    assert reasons[0]["reason"] == "package_derivation_receipt_digest_mismatch"


def test_derivation_reasons_use_default_code_for_empty_verification_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_derivation_payload(
        tmp_path,
        {"schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION},
    )
    _patch_derivation_verifiers(monkeypatch, verified=False)

    reasons = apply_gate_module._package_derivation_reasons(
        tmp_path,
        _summary_derivation(),
    )

    assert reasons[0]["reason"] == "package_derivation_mismatch"
    assert reasons[0]["detail"] == (
        "Authoritative package content differs from its receipt."
    )


def test_derivation_reasons_reject_noncanonical_summary_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_derivation_payload(
        tmp_path,
        {"schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION},
    )
    _patch_derivation_verifiers(monkeypatch, verified=True)

    reasons = apply_gate_module._package_derivation_reasons(
        tmp_path,
        _summary_derivation(receipt_path="wrong.json"),
    )

    assert reasons[0]["reason"] == "operator_summary_derivation_inconsistent"


@pytest.mark.parametrize(
    ("deck_directories", "reason"),
    ((0, "missing_deck_runtime_directory"), (2, "multiple_deck_runtime_directories")),
)
def test_required_structure_rejects_invalid_deck_directory_count(
    tmp_path: Path,
    deck_directories: int,
    reason: str,
) -> None:
    (tmp_path / "CustomConfig").mkdir()
    write_json(tmp_path / "reports" / "input_manifest.json", {})
    for index in range(deck_directories):
        (tmp_path / "CustomConfig" / f"deck-{index}").mkdir()

    reasons = apply_gate_module._required_package_structure_reasons(tmp_path, {})

    assert reasons[0]["reason"] == reason


def test_required_structure_rejects_missing_required_runtime_file(
    tmp_path: Path,
) -> None:
    (tmp_path / "CustomConfig" / "deck").mkdir(parents=True)
    write_json(tmp_path / "reports" / "input_manifest.json", {})

    reasons = apply_gate_module._required_package_structure_reasons(tmp_path, {})

    assert reasons[0]["reason"] == "missing_required_runtime_file"


@pytest.mark.parametrize(
    ("helper_name", "takes_summary"),
    (
        ("_actual_optional_surface_reasons", False),
        ("_actual_files_missing_from_summary_reasons", True),
        ("_summary_files_missing_from_actual_reasons", True),
        ("_actual_runtime_json_reasons", False),
    ),
)
def test_runtime_inventory_helpers_do_not_traverse_missing_custom_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    helper_name: str,
    takes_summary: bool,
) -> None:
    def unexpected_rglob(_path: Path, _pattern: str):
        raise AssertionError("missing CustomConfig must short-circuit inventory traversal")

    monkeypatch.setattr(Path, "rglob", unexpected_rglob)
    helper = getattr(apply_gate_module, helper_name)

    reasons = helper(tmp_path, {}) if takes_summary else helper(tmp_path)

    assert reasons == []


def test_summary_optional_surface_reasons_ignore_non_list_inventory() -> None:
    reasons = apply_gate_module._summary_optional_surface_reasons(
        {"generated_files": {"CustomConfig/deck/Combo.json": True}}
    )

    assert reasons == []


def test_actual_files_missing_from_summary_reports_empty_inventory(
    tmp_path: Path,
) -> None:
    runtime_file = tmp_path / "CustomConfig" / "deck" / "GlobalValues.json"
    write_json(runtime_file, {"GameCardId": "GlobalValues"})

    reasons = apply_gate_module._actual_files_missing_from_summary_reasons(
        tmp_path,
        {"generated_files": []},
    )

    assert reasons == [
        {
            "reason": "operator_summary_runtime_files_missing",
            "generated_file": str(runtime_file),
        }
    ]


def test_summary_missing_from_actual_reports_each_missing_runtime_file(
    tmp_path: Path,
) -> None:
    (tmp_path / "CustomConfig").mkdir()
    generated_file = "CustomConfig/deck/Missing.json"

    reasons = apply_gate_module._summary_files_missing_from_actual_reasons(
        tmp_path,
        {"generated_files": [generated_file]},
    )

    assert reasons == [
        {
            "reason": "operator_summary_runtime_file_missing",
            "generated_file": generated_file,
        }
    ]


def test_actual_runtime_json_reasons_report_invalid_two_part_json(
    tmp_path: Path,
) -> None:
    runtime_file = tmp_path / "CustomConfig" / "deck" / "Broken.json"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_bytes(b"{")

    reasons = apply_gate_module._actual_runtime_json_reasons(tmp_path)

    assert reasons[0]["reason"] == "invalid_runtime_json"
    assert reasons[0]["generated_file"] == "CustomConfig/deck/Broken.json"


def test_informational_reasons_are_suppressed_by_source_receipt_failure(
    tmp_path: Path,
) -> None:
    reasons = apply_gate_module._informational_reasons(
        tmp_path,
        summary={"semantic_status": "weak"},
        source_receipt_reasons=[{"reason": "source_invalid"}],
    )

    assert reasons == ()


def test_informational_reasons_accept_nonempty_source_receipts_without_warning(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "reports" / "guide_claim_bundle.json",
        {"canonical_source_receipts": [{"source_id": "guide"}]},
    )

    reasons = apply_gate_module._informational_reasons(
        tmp_path,
        summary={"semantic_status": "SOURCE_BACKED_STRONG"},
        source_receipt_reasons=[],
    )

    assert reasons == ()
