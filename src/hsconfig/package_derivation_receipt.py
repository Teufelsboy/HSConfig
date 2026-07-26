from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from hsconfig.io import read_json


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
_MANIFEST_LOCATION_KEYS = {
    "runtime_root",
    "cards_json",
    "claims_json",
    "guide_sources_json",
    "source_documents_json",
    "plan_reports_dir",
}
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


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
    if receipt.get("schema_version") != DERIVATION_RECEIPT_SCHEMA_VERSION:
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
            payload = _stable_manifest_projection(payload)
        else:
            payload = _stable_authority_value(payload)
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


def _stable_manifest_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _stable_authority_value(value)
        for key, value in sorted(manifest.items(), key=lambda item: str(item[0]))
        if str(key) not in _MANIFEST_LOCATION_KEYS
        and not _volatile_key(str(key))
    }


def _stable_authority_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stable_authority_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
            if not _volatile_key(str(key))
            and not _absolute_path_string(nested)
        }
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [
            _stable_authority_value(item)
            for item in value
            if not _absolute_path_string(item)
        ]
    return value


def _canonical_receipt_sequence(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise ValueError("Canonical source receipts must be a list.")
    receipts = [_stable_authority_value(item) for item in value]
    return sorted(receipts, key=_canonical_json_bytes)


def _volatile_key(key: str) -> bool:
    lowered = key.strip().lower()
    return (
        lowered in {"timestamp", "created_at", "generated_at", "updated_at"}
        or lowered.endswith("_timestamp")
    )


def _absolute_path_string(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return bool(
        _WINDOWS_ABSOLUTE_PATH.match(value)
        or value.startswith("\\\\")
        or value.startswith("/")
    )


def _canonical_json_sha256(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json_bytes(value)).hexdigest()}"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
