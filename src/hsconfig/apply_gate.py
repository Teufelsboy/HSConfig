from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from hsconfig.apply_decision import (
    ApplyDecision,
    ApplyFacts,
    apply_decision_payload,
    apply_decision_summary_projection,
    build_apply_decision,
)
from hsconfig.deck_input_verification import verify_deck_input
from hsconfig.io import read_json
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    DERIVATION_RECEIPT_SCHEMA_VERSION,
    deck_input_apply_eligibility_reasons,
    derivation_schema_version_supported,
    package_derivation_receipt_sha256,
    source_apply_eligibility_reasons,
    source_authority_reasons,
    verify_package_derivation_receipt,
)
from hsconfig.strict_package_validation import (
    LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
    LINKED_RUNTIME_OWNER_EVIDENCE_MISSING,
    strict_validation_passed,
    validate_complete_package,
)
from hsconfig.visionai_registry import NORMAL_PATH_FORBIDDEN_SURFACES


NORMAL_PATH_FORBIDDEN_SURFACE_NAMES = tuple(sorted(NORMAL_PATH_FORBIDDEN_SURFACES))
REQUIRED_RUNTIME_FILES = ("GlobalValues.json", "Mulligan.json")


def evaluate_apply_gate(
    package_root: str | Path,
    *,
    allow_source_informed: bool = False,
) -> dict[str, Any]:
    # Backward-compatible no-op; there is one recomputed decision path.
    del allow_source_informed
    package = Path(package_root)
    operator_path = package / "reports" / "operator_summary.json"
    if not operator_path.is_file():
        return _decision_gate(
            operator_path,
            build_apply_decision(
                _single_blocked_fact(
                    "package_summary_parity",
                    {
                        "reason": "missing_operator_summary",
                        "path": str(operator_path),
                    },
                )
            ),
        )

    try:
        summary = read_json(operator_path)
    except ValueError as error:
        return _decision_gate(
            operator_path,
            build_apply_decision(
                _single_blocked_fact(
                    "package_summary_parity",
                    {
                        "reason": "invalid_operator_summary_json",
                        "path": str(operator_path),
                        "error": str(error),
                    },
                )
            ),
        )
    if not isinstance(summary, dict):
        return _decision_gate(
            operator_path,
            build_apply_decision(
                _single_blocked_fact(
                    "package_summary_parity",
                    {
                        "reason": "invalid_operator_summary",
                        "path": str(operator_path),
                    },
                )
            ),
        )

    decision, _facts = recompute_apply_decision(
        package,
        summary,
        enforce_summary_core_fields=True,
    )
    return _decision_gate(operator_path, decision)


def recompute_apply_decision(
    package_root: str | Path,
    summary: dict[str, Any],
    *,
    enforce_summary_core_fields: bool,
) -> tuple[ApplyDecision, ApplyFacts]:
    package = Path(package_root)
    runtime_surface_reasons = [
        *_required_package_structure_reasons(package, summary),
        *_summary_optional_surface_reasons(summary),
        *_actual_optional_surface_reasons(package),
        *_actual_runtime_json_reasons(package),
    ]
    strict_reasons = _strict_package_validation_reasons(package)
    deck_input_reasons = _deck_input_verification_reasons(package, summary)
    source_receipt_reasons = source_authority_reasons(package)
    source_acquisition_reasons = source_apply_eligibility_reasons(package)
    derivation_reasons = _package_derivation_reasons(package, summary)
    package_summary_reasons = [
        *_actual_files_missing_from_summary_reasons(package, summary),
        *_summary_files_missing_from_actual_reasons(package, summary),
    ]
    informational_reasons = _informational_reasons(
        package,
        summary=summary,
        source_receipt_reasons=source_receipt_reasons,
    )
    blocking_reason_groups = (
        runtime_surface_reasons,
        strict_reasons,
        deck_input_reasons,
        source_receipt_reasons,
        source_acquisition_reasons,
        derivation_reasons,
        package_summary_reasons,
    )
    primary_blocking_reasons = next(
        (
            tuple(reasons)
            for reasons in blocking_reason_groups
            if reasons
        ),
        (),
    )
    facts = ApplyFacts(
        strict_package_validation=not strict_reasons,
        actual_runtime_surface_inventory=not runtime_surface_reasons,
        deck_input_verification=not deck_input_reasons,
        source_receipt_validity=not source_receipt_reasons,
        source_acquisition_eligibility=not source_acquisition_reasons,
        derivation_receipt_validity=not derivation_reasons,
        package_summary_parity=not package_summary_reasons,
        blocking_reasons=primary_blocking_reasons,
        informational_reasons=informational_reasons,
    )
    decision = build_apply_decision(facts)
    if not enforce_summary_core_fields:
        return decision, facts

    expected_core = apply_decision_summary_projection(decision, facts)
    core_parity_reasons = _summary_core_parity_reasons(summary, expected_core)
    if not core_parity_reasons:
        return decision, facts

    parity_facts = replace(
        facts,
        package_summary_parity=False,
        blocking_reasons=(
            *facts.blocking_reasons,
            *core_parity_reasons,
        ),
    )
    return build_apply_decision(parity_facts), parity_facts


def _deck_input_verification_reasons(
    package: Path,
    summary: dict[str, Any],
) -> list[dict[str, str]]:
    existing_reasons = deck_input_apply_eligibility_reasons(package)
    if existing_reasons:
        return existing_reasons
    try:
        manifest = read_json(package / "reports" / "input_manifest.json")
        deck_identity = read_json(package / "reports" / "deck_identity.json")
        if not isinstance(manifest, dict) or not isinstance(deck_identity, dict):
            raise ValueError("deck input authority documents must be objects")
        cards = deck_identity.get("cards")
        if not isinstance(cards, list):
            raise ValueError("deck identity cards must be a list")
        recomputed = verify_deck_input(
            deck_code=manifest.get("deck_code"),
            cards=cards,
            source=str(manifest.get("card_source") or ""),
        )
    except (OSError, TypeError, ValueError) as error:
        return [_deck_input_not_verified_reason(str(error))]

    persisted = manifest.get("deck_input_verification")
    summary_verification = summary.get("deck_input_verification")
    if (
        persisted != recomputed
        or summary_verification != recomputed
        or recomputed.get("runtime_apply_eligible") is not True
    ):
        return [
            _deck_input_not_verified_reason(
                "Persisted deck input verification is missing, ineligible, or stale."
            )
        ]
    return []


def _deck_input_not_verified_reason(detail: str) -> dict[str, str]:
    return {
        "reason": "deck_input_not_verified",
        "code": "deck_input_not_verified",
        "detail": detail or "Deck input is not eligible for runtime apply.",
    }


def _strict_package_validation_reasons(package: Path) -> list[dict[str, Any]]:
    try:
        report = validate_complete_package(package)
    except (OSError, TypeError, ValueError) as error:
        return [
            {
                "reason": "strict_package_validation_failed",
                "code": "strict_package_validation_failed",
                "detail": str(error),
            }
        ]
    if strict_validation_passed(report):
        return []
    errors = report.get("errors")
    normalized_errors = errors if isinstance(errors, list) else []
    linked_owner_code = next(
        (
            code
            for code in (
                LINKED_RUNTIME_OWNER_EVIDENCE_MISSING,
                LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
            )
            if code in normalized_errors
        ),
        None,
    )
    if linked_owner_code is not None:
        return [
            {
                "reason": linked_owner_code,
                "code": linked_owner_code,
                "detail": "Linked runtime owner evidence is unavailable or invalid.",
                "errors": normalized_errors,
            }
        ]
    return [
        {
            "reason": "strict_package_validation_failed",
            "code": "strict_package_validation_failed",
            "detail": "Strict package validation failed.",
            "errors": normalized_errors,
        }
    ]


def _package_derivation_reasons(
    package: Path,
    summary: dict[str, Any],
) -> list[dict[str, str]]:
    receipt_path = package / DERIVATION_RECEIPT_PATH
    summary_derivation = summary.get("package_derivation")
    if not receipt_path.is_file():
        return [
            {
                "reason": "package_derivation_receipt_missing",
                "code": "package_derivation_receipt_missing",
                "detail": "Package derivation receipt is missing.",
            }
        ]
    if not isinstance(summary_derivation, dict):
        return [
            {
                "reason": "operator_summary_derivation_inconsistent",
                "code": "operator_summary_derivation_inconsistent",
                "detail": "Operator summary does not reference package derivation.",
            }
        ]
    try:
        receipt = read_json(receipt_path)
    except ValueError:
        return [
            {
                "reason": "package_derivation_receipt_digest_mismatch",
                "code": "package_derivation_receipt_digest_mismatch",
                "detail": "Package derivation receipt is not valid JSON.",
            }
        ]
    if not isinstance(receipt, dict):
        return [
            {
                "reason": "package_derivation_receipt_digest_mismatch",
                "code": "package_derivation_receipt_digest_mismatch",
                "detail": "Package derivation receipt must be an object.",
            }
        ]
    if not derivation_schema_version_supported(receipt.get("schema_version")):
        return [
            {
                "reason": "package_derivation_receipt_schema_unsupported",
                "code": "package_derivation_receipt_schema_unsupported",
                "detail": "Package derivation receipt schema version is not supported.",
            }
        ]
    if (
        not derivation_schema_version_supported(
            summary_derivation.get("schema_version")
        )
        or summary_derivation.get("verified") is not True
    ):
        return [
            {
                "reason": "operator_summary_derivation_inconsistent",
                "code": "operator_summary_derivation_inconsistent",
                "detail": "Operator summary derivation metadata is inconsistent.",
            }
        ]
    actual_digest = package_derivation_receipt_sha256(receipt)
    if summary_derivation.get("receipt_sha256") != actual_digest:
        return [
            {
                "reason": "package_derivation_receipt_digest_mismatch",
                "code": "package_derivation_receipt_digest_mismatch",
                "detail": "Package derivation receipt digest does not match the operator summary.",
            }
        ]
    verified, verification_reasons = verify_package_derivation_receipt(
        package,
        receipt,
    )
    if not verified:
        first = verification_reasons[0] if verification_reasons else {}
        code = str(first.get("code") or "package_derivation_mismatch")
        return [
            {
                "reason": code,
                "code": code,
                "detail": str(
                    first.get(
                        "detail",
                        "Authoritative package content differs from its receipt.",
                    )
                ),
            }
        ]
    expected_summary_derivation = {
        "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
        "receipt_path": DERIVATION_RECEIPT_PATH,
        "receipt_sha256": actual_digest,
        "verified": True,
    }
    if summary_derivation != expected_summary_derivation:
        return [
            {
                "reason": "operator_summary_derivation_inconsistent",
                "code": "operator_summary_derivation_inconsistent",
                "detail": "Operator summary derivation metadata is inconsistent.",
            }
        ]
    return []


def _required_package_structure_reasons(
    package: Path, summary: dict[str, Any]
) -> list[dict[str, str]]:
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return [
            {
                "reason": "missing_custom_config_directory",
                "path": str(custom_config),
            }
        ]

    manifest = package / "reports" / "input_manifest.json"
    if not manifest.is_file():
        return [
            {
                "reason": "missing_input_manifest",
                "path": str(manifest),
            }
        ]

    deck_dirs = sorted(path for path in custom_config.iterdir() if path.is_dir())
    if not deck_dirs:
        return [
            {
                "reason": "missing_deck_runtime_directory",
                "path": str(custom_config),
            }
        ]
    if len(deck_dirs) > 1:
        return [
            {
                "reason": "multiple_deck_runtime_directories",
                "path": str(custom_config),
            }
        ]

    deck_dir = deck_dirs[0]
    for filename in REQUIRED_RUNTIME_FILES:
        required = deck_dir / filename
        if not required.is_file():
            return [
                {
                    "reason": "missing_required_runtime_file",
                    "path": str(required),
                }
            ]

    summary_files = _summary_generated_file_set(summary)
    for filename in REQUIRED_RUNTIME_FILES:
        key = _normalize_generated_file_path((deck_dir / filename).relative_to(package))
        if key not in summary_files:
            return [
                {
                    "reason": "required_runtime_file_not_in_operator_summary",
                    "generated_file": key,
                }
            ]
    return []


def _summary_optional_surface_reasons(summary: dict[str, Any]) -> list[dict[str, str]]:
    generated = summary.get("generated_files", [])
    if not isinstance(generated, list):
        return []
    reasons: list[dict[str, str]] = []
    for item in generated:
        generated_file = str(item)
        if generated_file.endswith(NORMAL_PATH_FORBIDDEN_SURFACE_NAMES):
            reasons.append(
                {
                    "reason": "normal_path_optional_surface_present",
                    "generated_file": generated_file,
                }
            )
    return reasons


def _actual_optional_surface_reasons(package: Path) -> list[dict[str, str]]:
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return []
    reasons: list[dict[str, str]] = []
    for path in sorted(path for path in custom_config.rglob("*") if path.is_file()):
        relative_parts = path.relative_to(custom_config).parts
        if len(relative_parts) != 2:
            reasons.append(
                {
                    "reason": "nested_runtime_file_present",
                    "generated_file": str(path),
                }
            )
            continue
        if path.name in NORMAL_PATH_FORBIDDEN_SURFACES:
            reasons.append(
                {
                    "reason": "normal_path_optional_surface_present",
                    "generated_file": str(path),
                }
            )
    return reasons


def _actual_files_missing_from_summary_reasons(
    package: Path, summary: dict[str, Any]
) -> list[dict[str, str]]:
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return []

    summary_files = _summary_generated_file_set(summary)
    reasons: list[dict[str, str]] = []
    actual_files = [
        path
        for path in sorted(path for path in custom_config.rglob("*") if path.is_file())
        if len(path.relative_to(custom_config).parts) == 2
        and path.name not in NORMAL_PATH_FORBIDDEN_SURFACES
    ]
    if actual_files and not summary_files:
        return [
            {
                "reason": "operator_summary_runtime_files_missing",
                "generated_file": str(actual_files[0]),
            }
        ]
    for path in actual_files:
        relative_parts = path.relative_to(custom_config).parts
        if len(relative_parts) != 2:
            continue
        summary_key = _normalize_generated_file_path(path.relative_to(package))
        if summary_key not in summary_files:
            reasons.append(
                {
                    "reason": "actual_runtime_file_not_in_operator_summary",
                    "generated_file": str(path),
                }
            )
    return reasons


def _summary_files_missing_from_actual_reasons(
    package: Path, summary: dict[str, Any]
) -> list[dict[str, str]]:
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return []

    actual_files = {
        _normalize_generated_file_path(path.relative_to(package))
        for path in custom_config.rglob("*")
        if path.is_file()
    }
    reasons: list[dict[str, str]] = []
    for generated_file in sorted(_summary_generated_file_set(summary)):
        if generated_file.replace("\\", "/").rsplit("/", 1)[-1] in NORMAL_PATH_FORBIDDEN_SURFACES:
            continue
        if generated_file not in actual_files:
            reasons.append(
                {
                    "reason": "operator_summary_runtime_file_missing",
                    "generated_file": generated_file,
                }
            )
    return reasons


def _actual_runtime_json_reasons(package: Path) -> list[dict[str, str]]:
    custom_config = package / "CustomConfig"
    if not custom_config.is_dir():
        return []

    reasons: list[dict[str, str]] = []
    for path in sorted(path for path in custom_config.rglob("*") if path.is_file()):
        relative_parts = path.relative_to(custom_config).parts
        if len(relative_parts) != 2 or path.name in NORMAL_PATH_FORBIDDEN_SURFACES:
            continue
        try:
            read_json(path)
        except ValueError as error:
            reasons.append(
                {
                    "reason": "invalid_runtime_json",
                    "generated_file": _normalize_generated_file_path(
                        path.relative_to(package)
                    ),
                    "path": str(path),
                    "error": str(error),
                }
            )
    return reasons


def _summary_generated_file_set(summary: dict[str, Any]) -> set[str]:
    generated = summary.get("generated_files", [])
    if not isinstance(generated, list):
        return set()
    return {
        _normalize_generated_file_path(Path(str(item)))
        for item in generated
        if str(item).replace("\\", "/").startswith("CustomConfig/")
    }


def _normalize_generated_file_path(path: Path) -> str:
    return path.as_posix().replace("\\", "/")


def _informational_reasons(
    package: Path,
    *,
    summary: dict[str, Any],
    source_receipt_reasons: list[dict[str, str]],
) -> tuple[dict[str, Any], ...]:
    reasons: list[dict[str, Any]] = []
    if source_receipt_reasons:
        return tuple(reasons)
    try:
        bundle = read_json(package / "reports" / "guide_claim_bundle.json")
    except (OSError, ValueError):
        bundle = None
    if isinstance(bundle, dict):
        receipts = bundle.get(
            "canonical_source_receipts",
            bundle.get("globalvalues_source_receipts", []),
        )
        if isinstance(receipts, list) and not receipts:
            reasons.append(
                {
                    "reason": "exact_source_not_closed",
                    "blocking": False,
                }
            )
    if str(summary.get("semantic_status", "")) != "SOURCE_BACKED_STRONG":
        reasons.append(
            {
                "reason": "semantic_strength_incomplete",
                "blocking": False,
            }
        )
    return tuple(reasons)


def _summary_core_parity_reasons(
    summary: dict[str, Any],
    expected_core: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatched_fields = [
        field
        for field, expected in expected_core.items()
        if summary.get(field) != expected
    ]
    if not mismatched_fields:
        return []
    return [
        {
            "reason": "operator_summary_apply_decision_mismatch",
            "code": "operator_summary_apply_decision_mismatch",
            "fields": mismatched_fields,
        }
    ]


def _single_blocked_fact(
    fact_name: str,
    reason: dict[str, Any],
) -> ApplyFacts:
    values = {
        "strict_package_validation": True,
        "actual_runtime_surface_inventory": True,
        "deck_input_verification": True,
        "source_receipt_validity": True,
        "source_acquisition_eligibility": True,
        "derivation_receipt_validity": True,
        "package_summary_parity": True,
    }
    values[fact_name] = False
    return ApplyFacts(
        **values,
        blocking_reasons=(reason,),
    )


def _decision_gate(
    operator_path: Path,
    decision: ApplyDecision,
) -> dict[str, Any]:
    payload = apply_decision_payload(decision)
    return {
        "status": "allowed" if decision.allowed else "blocked",
        "operator_summary_path": str(operator_path),
        **payload,
    }
