from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import json
from typing import Any

from hsconfig.disposition_ledger import (
    build_disposition_ledger,
    build_dual_closure,
)
from hsconfig.globalvalues_decisions import (
    build_globalvalues_decision_ledger,
    canonical_globalvalues_baseline_sha256,
)
from hsconfig.io import read_json, write_json
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    refresh_package_derivation_authority,
)
from hsconfig.pre_run_metrics import (
    PRE_RUN_CONTRACT_SCHEMA_VERSION,
    build_layered_evidence_contract_report,
    build_pre_run_closure_report,
    build_source_acquisition_closure_report,
    disposition_ledger_document,
    globalvalues_decision_report_document,
    pre_emission_expectations_from_audit,
    source_acquisition_input_binding,
    verified_emission_input_from_physical_rows,
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
    write_current_pre_run_contract(package)

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


def write_current_pre_run_contract(package: Path) -> None:
    deck_identity = read_json(package / "reports" / "deck_identity.json")
    if not isinstance(deck_identity, Mapping):
        raise AssertionError("Deck identity fixture must be an object")
    reports = package / "reports"
    fingerprint = str(deck_identity["deck_fingerprint"])
    cards = deck_identity.get("main_deck", deck_identity.get("cards", ()))
    evidence_cards = [
        {
            "composite_card_key": (
                f"{fingerprint}:main_deck:{card['card_id']}"
            ),
            "zone": "main_deck",
            "official_semantics_canonical_json": json.dumps(
                {"GameCardId": card["card_id"]},
                separators=(",", ":"),
                sort_keys=True,
            ),
            "authority_lane": "E",
            "evidence_ids": ["policy:BOT_NATIVE_PRE_RUN"],
            "claim_ids": [],
            "physical_owner": card["card_id"],
        }
        for card in cards
        if isinstance(card, Mapping) and card.get("card_id")
    ]
    disposition = build_disposition_ledger(
        evidence_contract={
            "deck_fingerprint": fingerprint,
            "cards": evidence_cards,
            "claim_ids": [],
        },
        claim_lifecycle_rows=[],
        physical_emission_index={},
        runtime_surface_ledger={"physical_emissions": []},
    )
    baseline = read_json(reports / "globalvalues_baseline.json")
    authority_matrix = read_json(
        reports / "global_values_authority_matrix.json"
    )
    globalvalues = build_globalvalues_decision_ledger(
        deck_fingerprint=fingerprint,
        baseline=baseline,
        baseline_sha256=canonical_globalvalues_baseline_sha256(
            baseline
        ),
        authority_matrix=authority_matrix,
    )
    source_audit = {
        "claim_rows": {},
        "claim_lifecycle_rows": [],
    }
    runtime_ledger = read_json(
        reports / "runtime_surface_ledger.json"
    )
    observations: set[tuple[str, str]] = set()
    for card_id, row in runtime_ledger.get("cards", {}).items():
        if not isinstance(row, Mapping):
            continue
        observations.update(
            (str(card_id), str(path))
            for path in row.get("runtime_surfaces", ())
            if str(path) == f"{card_id}.json"
        )
    for runtime_card_id, row in runtime_ledger.get(
        "linked_runtime_entities",
        {},
    ).items():
        if not isinstance(row, Mapping):
            continue
        path = str(
            row.get("runtime_surface")
            or f"{runtime_card_id}.json"
        )
        if row.get("runtime_emitted") is True:
            observations.add((str(runtime_card_id), path))
    expectations = pre_emission_expectations_from_audit(
        disposition_ledger=disposition,
        source_contract_audit=source_audit,
    )
    verified = verified_emission_input_from_physical_rows(
        disposition_ledger=disposition,
        physical_rows=tuple(
            {
                "physical_owner": owner,
                "relative_path": path,
                "meaningful": True,
                "schema_supported": True,
            }
            for owner, path in sorted(observations)
        ),
        rejected_rows=(
            *runtime_ledger.get("physical_errors", ()),
            *runtime_ledger.get("unexpected_runtime_emissions", ()),
            *runtime_ledger.get(
                "linked_runtime_owner_collisions",
                (),
            ),
        ),
        semantic_expectations=expectations,
    )
    layered = build_layered_evidence_contract_report(
        disposition_ledger=disposition,
        classified_authorities={},
    )
    acquisition = build_source_acquisition_closure_report(
        deck_fingerprint=fingerprint,
        acquisition_closure=None,
    )
    dual_closure = build_dual_closure(
        dispositions=disposition,
        globalvalues_ledger=globalvalues,
        strategy_source_status="partial",
    )
    pre_run = build_pre_run_closure_report(
        disposition_ledger=disposition,
        globalvalues_ledger=globalvalues,
        dual_closure=dual_closure,
        layered_evidence_report=layered,
        source_acquisition_report=acquisition,
        verified_emissions=verified,
    )
    write_json(
        reports / "source_contract_audit.json",
        source_audit,
    )
    write_json(
        reports / "disposition_ledger.json",
        disposition_ledger_document(disposition),
    )
    write_json(
        reports / "globalvalues_decision_ledger.json",
        globalvalues_decision_report_document(globalvalues),
    )
    write_json(
        reports / "layered_evidence_contract.json",
        layered,
    )
    write_json(
        reports / "source_acquisition_closure.json",
        acquisition,
    )
    write_json(reports / "pre_run_closure.json", pre_run)
    manifest_path = reports / "input_manifest.json"
    manifest = read_json(manifest_path)
    manifest["pre_run_contract_schema_version"] = (
        PRE_RUN_CONTRACT_SCHEMA_VERSION
    )
    manifest["source_acquisition_input_binding"] = (
        source_acquisition_input_binding(acquisition)
    )
    write_json(manifest_path, manifest)
