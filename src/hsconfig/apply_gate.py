from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.deck_input_verification import verify_deck_input
from hsconfig.io import read_json
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    DERIVATION_RECEIPT_SCHEMA_VERSION,
    deck_input_apply_eligibility_reasons,
    derivation_schema_version_supported,
    package_derivation_receipt_sha256,
    source_authority_reasons,
    verify_package_derivation_receipt,
)
from hsconfig.strict_package_validation import (
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
    # Backward-compatible no-op; operator_summary is the gate.
    del allow_source_informed
    package = Path(package_root)
    operator_path = package / "reports" / "operator_summary.json"
    if not operator_path.is_file():
        return _blocked(
            operator_path,
            {
                "reason": "missing_operator_summary",
                "path": str(operator_path),
            },
        )

    try:
        summary = read_json(operator_path)
    except ValueError as error:
        return _blocked(
            operator_path,
            {
                "reason": "invalid_operator_summary_json",
                "path": str(operator_path),
                "error": str(error),
            },
        )
    if not isinstance(summary, dict):
        return _blocked(
            operator_path,
            {
                "reason": "invalid_operator_summary",
                "path": str(operator_path),
            },
        )

    structure_reasons = _required_package_structure_reasons(package, summary)
    if structure_reasons:
        return _blocked(operator_path, *structure_reasons)

    strict_surface_reasons = [
        *_summary_optional_surface_reasons(summary),
        *_actual_optional_surface_reasons(package),
    ]
    if strict_surface_reasons:
        return _blocked(operator_path, *strict_surface_reasons)

    runtime_json_reasons = _actual_runtime_json_reasons(package)
    if runtime_json_reasons:
        return _blocked(operator_path, *runtime_json_reasons)

    strict_reasons = _strict_package_validation_reasons(package)
    if strict_reasons:
        return _blocked(operator_path, *strict_reasons)

    deck_input_reasons = _deck_input_verification_reasons(package, summary)
    if deck_input_reasons:
        return _blocked(operator_path, *deck_input_reasons)

    source_reasons = source_authority_reasons(package)
    if source_reasons:
        return _blocked(operator_path, *source_reasons)

    derivation_reasons = _package_derivation_reasons(package, summary)
    if derivation_reasons:
        return _blocked(operator_path, *derivation_reasons)

    summary_parity_reasons = [
        *_actual_files_missing_from_summary_reasons(package, summary),
        *_summary_files_missing_from_actual_reasons(package, summary),
    ]
    if summary_parity_reasons:
        return _blocked(operator_path, *summary_parity_reasons)

    technical_status = str(summary.get("technical_status", ""))
    semantic_status = str(summary.get("semantic_status", ""))
    next_action = str(summary.get("next_action", ""))
    apply_policy = str(summary.get("apply_policy", ""))

    if technical_status == "VALID_PACKAGE":
        return _allowed(
            operator_path,
            mode="load_safe_apply",
            reasons=[
                {
                    "reason": "runtime_load_safe_package",
                    "technical_status": technical_status,
                    "semantic_status": semantic_status,
                    "next_action": next_action,
                    "apply_policy": apply_policy,
                    "semantic_blocker_count": _list_count(
                        summary.get("semantic_blockers", [])
                    ),
                }
            ],
        )

    return _blocked(
        operator_path,
        {
            "reason": "operator_summary_not_valid_package",
            "technical_status": technical_status,
            "semantic_status": semantic_status,
            "next_action": next_action,
            "apply_policy": apply_policy,
        },
    )


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
    return [
        {
            "reason": "strict_package_validation_failed",
            "code": "strict_package_validation_failed",
            "detail": "Strict package validation failed.",
            "errors": errors if isinstance(errors, list) else [],
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


def _allowed(
    operator_path: Path,
    *,
    mode: str,
    reasons: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "allowed",
        "allowed": True,
        "operator_summary_path": str(operator_path),
        "mode": mode,
        "reasons": reasons,
    }


def _blocked(operator_path: Path, *reasons: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "blocked",
        "allowed": False,
        "operator_summary_path": str(operator_path),
        "mode": "blocked",
        "reasons": list(reasons),
    }


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0
