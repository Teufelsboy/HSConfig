from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
from typing import Any

from hsconfig.io import read_json
from hsconfig.source_acquisition_provenance import (
    strategic_source_provenance_is_verified,
)
from hsconfig.strict_package_validation import (
    strict_validation_passed,
    validate_complete_package,
)


DERIVATION_RECEIPT_SCHEMA_VERSION = 1
DERIVATION_RECEIPT_PATH = "package_derivation_receipt.json"

_AUTHORITATIVE_JSON_PATHS = (
    "reports/input_manifest.json",
    "reports/deck_identity.json",
    "reports/deck_fingerprint.json",
    "reports/globalvalues_baseline.json",
    "reports/globalvalues_profile.json",
    "reports/output_ownership_manifest.json",
)
_AUTHORITY_EXCLUDED_TOP_LEVEL_FIELDS = {
    "reports/input_manifest.json": frozenset(
        {
            "runtime_root",
            "cards_json",
            "claims_json",
            "guide_sources_json",
            "source_documents_json",
            "plan_reports_dir",
            "timestamp",
            "created_at",
            "generated_at",
            "updated_at",
        }
    ),
    "reports/deck_identity.json": frozenset(
        {"timestamp", "created_at", "generated_at", "updated_at"}
    ),
    "reports/deck_fingerprint.json": frozenset(
        {"timestamp", "created_at", "generated_at", "updated_at"}
    ),
    "reports/globalvalues_baseline.json": frozenset(
        {"timestamp", "created_at", "generated_at", "updated_at"}
    ),
    "reports/globalvalues_profile.json": frozenset(
        {"timestamp", "created_at", "generated_at", "updated_at"}
    ),
    "reports/output_ownership_manifest.json": frozenset(
        {"timestamp", "created_at", "generated_at", "updated_at"}
    ),
}


def derivation_schema_version_supported(value: Any) -> bool:
    return type(value) is int and value == DERIVATION_RECEIPT_SCHEMA_VERSION


def build_package_derivation_receipt(
    package_root: Path,
) -> dict[str, Any]:
    package = Path(package_root)
    return {
        "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
        "inputs": _authoritative_input_digests(package),
        "runtime_files": _runtime_file_digests(package),
    }


def verify_package_derivation_receipt(
    package_root: Path,
    receipt: Mapping[str, Any],
) -> tuple[bool, list[dict[str, str]]]:
    if not derivation_schema_version_supported(receipt.get("schema_version")):
        return False, [
            {
                "code": "package_derivation_receipt_schema_unsupported",
                "detail": "Package derivation receipt schema version is not supported.",
            }
        ]
    try:
        expected = build_package_derivation_receipt(Path(package_root))
    except (OSError, TypeError, ValueError):
        return False, [
            {
                "code": "package_derivation_mismatch",
                "detail": "Authoritative package content differs from its receipt.",
            }
        ]
    if dict(receipt) != expected:
        return False, [
            {
                "code": "package_derivation_mismatch",
                "detail": "Authoritative package content differs from its receipt.",
            }
        ]
    return True, []


def canonical_package_derivation_receipt_bytes(
    receipt: Mapping[str, Any],
) -> bytes:
    return _canonical_json_bytes(dict(receipt))


def package_derivation_receipt_sha256(
    receipt: Mapping[str, Any],
) -> str:
    canonical = canonical_package_derivation_receipt_bytes(receipt)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def write_package_derivation_receipt(
    path: str | Path,
    receipt: Mapping[str, Any],
) -> str:
    canonical = canonical_package_derivation_receipt_bytes(receipt)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(canonical)
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def refresh_package_derivation_authority(
    package_root: str | Path,
) -> dict[str, Any]:
    package = Path(package_root)
    receipt = build_package_derivation_receipt(package)
    verified, reasons = verify_package_derivation_receipt(package, receipt)
    digest = write_package_derivation_receipt(
        package / DERIVATION_RECEIPT_PATH,
        receipt,
    )
    authority: dict[str, Any] = {
        "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
        "receipt_path": DERIVATION_RECEIPT_PATH,
        "receipt_sha256": digest,
        "verified": verified,
    }
    if reasons:
        authority["reasons"] = reasons
    return authority


def deck_input_apply_eligibility_reasons(
    package_root: str | Path,
) -> list[dict[str, str]]:
    package = Path(package_root)
    manifest_path = package / "reports" / "input_manifest.json"
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError):
        return []
    if not isinstance(manifest, dict):
        return []
    verification = manifest.get("deck_input_verification")
    verification_path = package / "reports" / "deck_input_verification.json"
    if verification_path.is_file():
        try:
            verification = read_json(verification_path)
        except ValueError:
            verification = {"runtime_apply_eligible": False}
    if not isinstance(verification, dict):
        return []
    if verification.get("runtime_apply_eligible") is True:
        return []
    return [
        {
            "reason": "deck_input_not_verified",
            "code": "deck_input_not_verified",
            "detail": "Deck input is not eligible for runtime apply.",
        }
    ]


def source_authority_reasons(
    package_root: str | Path,
) -> list[dict[str, str]]:
    package = Path(package_root)
    bundle_path = package / "reports" / "guide_claim_bundle.json"
    if not bundle_path.is_file():
        return []
    try:
        bundle = read_json(bundle_path)
    except ValueError:
        return [
            {
                "reason": "source_authority_receipt_invalid",
                "code": "source_authority_receipt_invalid",
                "detail": "Canonical source receipt container is invalid.",
            }
        ]
    if not isinstance(bundle, dict):
        return [
            {
                "reason": "source_authority_receipt_invalid",
                "code": "source_authority_receipt_invalid",
                "detail": "Canonical source receipt container is invalid.",
            }
        ]
    receipts = bundle.get(
        "canonical_source_receipts",
        bundle.get("globalvalues_source_receipts", []),
    )
    if not isinstance(receipts, list):
        return [
            {
                "reason": "source_authority_receipt_invalid",
                "code": "source_authority_receipt_invalid",
                "detail": "Canonical source receipts must be a list.",
            }
        ]
    for receipt in receipts:
        if (
            not isinstance(receipt, dict)
            or receipt.get("receipt_kind")
            != "canonical_exact_deck_source_document"
            or not strategic_source_provenance_is_verified(
                receipt.get("acquisition_provenance")
            )
        ):
            return [
                {
                    "reason": "source_authority_receipt_invalid",
                    "code": "source_authority_receipt_invalid",
                    "detail": "Canonical source receipt is not live verified.",
                }
            ]
    return []


def build_package_authority_context(
    package_root: str | Path,
) -> dict[str, Any]:
    package = Path(package_root)
    final_strict_validation_report = validate_complete_package(package)
    receipt_verified = False
    receipt_sha256: str | None = None
    try:
        receipt = read_json(package / DERIVATION_RECEIPT_PATH)
    except (OSError, ValueError):
        receipt = None
    if isinstance(receipt, Mapping):
        receipt_sha256 = package_derivation_receipt_sha256(receipt)
        receipt_verified, _reasons = verify_package_derivation_receipt(
            package,
            receipt,
        )
    return {
        "strict_validation_passed": strict_validation_passed(
            final_strict_validation_report
        ),
        "deck_input_apply_eligible": not deck_input_apply_eligibility_reasons(
            package
        ),
        "source_authority_verified": not source_authority_reasons(package),
        "derivation_receipt_verified": receipt_verified,
        "receipt_sha256": receipt_sha256,
    }


def package_authority_context_verified(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return all(
        value.get(key) is True
        for key in (
            "strict_validation_passed",
            "deck_input_apply_eligible",
            "source_authority_verified",
            "derivation_receipt_verified",
        )
    )


def _authoritative_input_digests(package_root: Path) -> dict[str, str]:
    inputs: dict[str, str] = {}
    manifest: Mapping[str, Any] | None = None
    for relative_path in _AUTHORITATIVE_JSON_PATHS:
        path = package_root / Path(relative_path)
        payload = read_json(path)
        if not isinstance(payload, Mapping):
            raise ValueError(f"Authoritative package input must be an object: {path}")
        if relative_path == "reports/input_manifest.json":
            manifest = payload
        payload = _stable_authority_document(relative_path, payload)
        inputs[relative_path] = _canonical_json_sha256(payload)

    guide_bundle_path = package_root / "reports" / "guide_claim_bundle.json"
    guide_bundle = read_json(guide_bundle_path)
    if not isinstance(guide_bundle, Mapping):
        raise ValueError(
            f"Authoritative source receipt container must be an object: {guide_bundle_path}"
        )
    source_receipts = guide_bundle.get(
        "canonical_source_receipts",
        guide_bundle.get("globalvalues_source_receipts", []),
    )
    inputs["reports/guide_claim_bundle.json#canonical_source_receipts"] = (
        _canonical_json_sha256(_canonical_receipt_sequence(source_receipts))
    )

    deck_input_verification_path = (
        package_root / "reports" / "deck_input_verification.json"
    )
    if deck_input_verification_path.is_file():
        deck_input_verification = read_json(deck_input_verification_path)
    else:
        deck_input_verification = (
            manifest.get("deck_input_verification")
            if isinstance(manifest, Mapping)
            else None
        )
    inputs["deck_input_verification"] = _canonical_json_sha256(
        _stable_authority_value(deck_input_verification)
    )
    return dict(sorted(inputs.items()))


def _runtime_file_digests(package_root: Path) -> dict[str, str]:
    custom_config = package_root / "CustomConfig"
    runtime_files: dict[str, str] = {}
    if not custom_config.is_dir():
        return runtime_files
    for path in sorted(
        (item for item in custom_config.rglob("*.json") if item.is_file()),
        key=lambda item: item.relative_to(package_root).as_posix(),
    ):
        payload = read_json(path)
        relative_path = path.relative_to(package_root).as_posix()
        runtime_files[relative_path] = _canonical_json_sha256(payload)
    return runtime_files


def _stable_authority_document(
    relative_path: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    excluded_fields = _AUTHORITY_EXCLUDED_TOP_LEVEL_FIELDS.get(
        relative_path,
        frozenset(),
    )
    return {
        str(key): _stable_authority_value(value)
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
        if str(key) not in excluded_fields
    }


def _stable_authority_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stable_authority_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [
            _stable_authority_value(item)
            for item in value
        ]
    return value


def _canonical_receipt_sequence(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise ValueError("Canonical source receipts must be a list.")
    receipts = [_stable_authority_value(item) for item in value]
    return sorted(receipts, key=_canonical_json_bytes)


def _canonical_json_sha256(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json_bytes(value)).hexdigest()}"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
