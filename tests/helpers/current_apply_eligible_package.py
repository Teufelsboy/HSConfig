from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from hsconfig.io import read_json, write_json
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    refresh_package_derivation_authority,
)
from hsconfig.source_document_model import source_claim_signature
from tests.helpers.current_globalvalues_contract import (
    write_current_globalvalues_contract,
)
from tests.helpers.current_runtime_surface_ledger_contract import (
    RUNTIME_SURFACE_LEDGER_PATH,
    write_current_runtime_surface_ledger,
)
from tests.helpers.live_acquisition import acquire_live_test_provenance
from tests.helpers.verified_deck_input import (
    install_verified_deck_input,
    install_verified_deckstring_input,
)


DEFAULT_RUNTIME_FILES: dict[str, dict[str, Any]] = {
    "GlobalValues.json": {
        "GameCardId": "GlobalValues",
        "ConfigComment": "current apply-eligible fixture",
    },
    "Mulligan.json": {
        "GameCardId": "Mulligan",
        "ConfigComment": "current apply-eligible fixture",
        "Mulligan": {"values": []},
    },
}


def write_current_apply_eligible_package(
    package: Path,
    *,
    operator_summary: Mapping[str, Any] | None = None,
    runtime_files: Mapping[str, Mapping[str, Any]] | None = None,
    generated_files: Sequence[str] | None = None,
    deck_directory: str = "deck",
    deck_name: str = "deck",
    deck_code: str | None = None,
) -> Path:
    """Write or finalize a minimal package using every current apply authority."""

    package = Path(package)
    deck_dir = package / "CustomConfig" / deck_directory
    reports = package / "reports"
    if runtime_files is not None or not deck_dir.is_dir():
        files = dict(DEFAULT_RUNTIME_FILES)
        if runtime_files:
            files.update(
                {
                    str(filename): dict(payload)
                    for filename, payload in runtime_files.items()
                }
            )
        for filename, payload in files.items():
            write_json(deck_dir / filename, payload)

    manifest_path = reports / "input_manifest.json"
    if not manifest_path.is_file():
        write_json(
            manifest_path,
            {
                "deck_name": deck_name,
                "runtime_root": "unused",
            },
        )
    if deck_code is None:
        deck_input_verification = install_verified_deck_input(
            package,
            deck_name=deck_name,
        )
    else:
        deck_input_verification = install_verified_deckstring_input(
            package,
            deck_name=deck_name,
            deck_code=deck_code,
        )
    deck_identity = read_json(reports / "deck_identity.json")
    if not isinstance(deck_identity, dict):
        raise AssertionError("Deck identity fixture must be an object")

    globalvalues = read_json(deck_dir / "GlobalValues.json")
    if not isinstance(globalvalues, dict):
        raise AssertionError("GlobalValues fixture must be an object")
    write_current_globalvalues_contract(package, globalvalues)

    live_provenance = acquire_live_test_provenance()
    identity_cards = deck_identity.get("cards")
    first_card_id = ""
    if isinstance(identity_cards, list) and identity_cards:
        first_card = identity_cards[0]
        if isinstance(first_card, Mapping):
            first_card_id = str(first_card.get("card_id", ""))
    source_ref = "source:current-apply-eligible-fixture"
    source_url = "https://example.test/acquisition"
    deck_fingerprint = str(deck_identity.get("deck_fingerprint", ""))
    claim = {
        "claim_id": "claim_current_apply_eligible",
        "claim_kind": "card_role",
        "cards": [first_card_id] if first_card_id else [],
        "source_refs": [source_ref, source_url],
        "source_url": source_url,
        "source_confidence": "high",
        "deck_match": {
            "exact_deck_evidence": {
                "matched": True,
                "matched_deck_fingerprint": deck_fingerprint,
            }
        },
        "acquisition_provenance": live_provenance,
    }
    write_json(
        reports / "guide_claim_bundle.json",
        {
            "claims": [claim],
            "source_evidence_index": [
                {
                    "source_ref": source_ref,
                    "source_url": source_url,
                    "acquisition_provenance": live_provenance,
                }
            ],
            "canonical_source_receipts": [
                {
                    "receipt_kind": "canonical_exact_deck_source_document",
                    "source_ref": source_ref,
                    "source_url": source_url,
                    "matched_deck_fingerprint": deck_fingerprint,
                    "claim_id": claim["claim_id"],
                    "claim_signature": source_claim_signature(claim),
                    "acquisition_provenance": live_provenance,
                }
            ]
        },
    )
    behavior_plan_path = reports / "card_behavior_plan_report.json"
    if not behavior_plan_path.is_file():
        write_json(behavior_plan_path, {"rows": []})

    write_current_runtime_surface_ledger(package)

    actual_runtime_files = sorted(
        path.relative_to(package).as_posix()
        for path in deck_dir.glob("*.json")
        if path.is_file()
    )
    summary_generated_files = (
        [str(path).replace("\\", "/") for path in generated_files]
        if generated_files is not None
        else actual_runtime_files
    )
    ownership_files = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file()
    }
    ownership_files.update(
        {
            *summary_generated_files,
            DERIVATION_RECEIPT_PATH,
            RUNTIME_SURFACE_LEDGER_PATH,
            "reports/operator_summary.json",
            "reports/output_ownership_manifest.json",
        }
    )
    write_json(
        reports / "output_ownership_manifest.json",
        build_output_ownership_manifest(sorted(ownership_files)),
    )
    package_derivation = refresh_package_derivation_authority(package)

    summary = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "next_action": "READY_TO_APPLY_OR_HANDOFF",
        "apply_policy": "ALLOWED",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_reason": "runtime_load_safe_package",
        "semantic_blockers": [],
        **dict(operator_summary or {}),
        "generated_files": summary_generated_files,
        "deck_input_verification": deck_input_verification,
        "package_derivation": package_derivation,
    }
    write_json(reports / "operator_summary.json", summary)
    return package
