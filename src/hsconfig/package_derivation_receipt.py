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
from hsconfig.source_document_model import (
    source_claim_signature,
    strategic_source_receipt_provenance,
)
from hsconfig.strict_package_validation import (
    linked_runtime_owner_projection,
    strict_validation_passed,
    validate_complete_package,
)


DERIVATION_RECEIPT_SCHEMA_VERSION = 2
DERIVATION_RECEIPT_PATH = "package_derivation_receipt.json"

_AUTHORITATIVE_JSON_PATHS = (
    "reports/input_manifest.json",
    "reports/deck_identity.json",
    "reports/deck_fingerprint.json",
    "reports/globalvalues_baseline.json",
    "reports/globalvalues_profile.json",
    "reports/card_behavior_plan_report.json",
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
        "linked_runtime_owners": _linked_runtime_owners(package),
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
    reasons, _canonical_receipt_count = _source_authority_state(
        Path(package_root)
    )
    return reasons


def canonical_source_receipt_reasons(
    *,
    bundle: Mapping[str, Any],
    deck_identity: Mapping[str, Any],
) -> list[dict[str, str]]:
    receipts = bundle.get(
        "canonical_source_receipts",
        bundle.get("globalvalues_source_receipts", []),
    )
    if not isinstance(receipts, list):
        return [_source_authority_invalid_reason()]
    if not receipts:
        return []

    claims = bundle.get("claims", [])
    claim_rows = (
        claims
        if isinstance(claims, Sequence)
        and not isinstance(claims, (str, bytes, bytearray))
        else ()
    )
    source_evidence = bundle.get("source_evidence_index", [])
    source_evidence_rows = (
        source_evidence
        if isinstance(source_evidence, Sequence)
        and not isinstance(source_evidence, (str, bytes, bytearray))
        else ()
    )
    target_fingerprint = _clean_text(
        deck_identity.get("deck_fingerprint")
    )
    seen_claim_ids: set[str] = set()

    for receipt in receipts:
        if not isinstance(receipt, Mapping):
            return [_source_authority_invalid_reason()]
        if (
            receipt.get("receipt_kind")
            != "canonical_exact_deck_source_document"
            or not strategic_source_provenance_is_verified(
                receipt.get("acquisition_provenance")
            )
        ):
            return [_source_authority_invalid_reason()]

        claim_id = _clean_text(receipt.get("claim_id"))
        if not claim_id:
            return [
                _source_receipt_reason(
                    "source_receipt_claim_missing",
                    "Canonical source receipt has no claim identity.",
                )
            ]
        if claim_id in seen_claim_ids:
            return [
                _source_receipt_reason(
                    "source_receipt_duplicate",
                    "Canonical source receipt claim identity is duplicated.",
                )
            ]
        seen_claim_ids.add(claim_id)

        matching_claims = [
            claim
            for claim in claim_rows
            if isinstance(claim, Mapping)
            and _clean_text(claim.get("claim_id")) == claim_id
        ]
        if len(matching_claims) != 1:
            return [
                _source_receipt_reason(
                    "source_receipt_claim_missing",
                    "Canonical source receipt does not resolve to one claim.",
                )
            ]
        claim = matching_claims[0]

        if _clean_text(receipt.get("claim_signature")) != source_claim_signature(
            claim
        ):
            return [
                _source_receipt_reason(
                    "source_receipt_signature_mismatch",
                    "Canonical source receipt signature does not match its claim.",
                )
            ]

        receipt_fingerprint = _clean_text(
            receipt.get("matched_deck_fingerprint")
        )
        claim_fingerprint = _claim_deck_fingerprint(claim)
        if (
            not target_fingerprint
            or receipt_fingerprint != target_fingerprint
            or claim_fingerprint != target_fingerprint
        ):
            return [
                _source_receipt_reason(
                    "source_receipt_deck_mismatch",
                    "Canonical source receipt is not bound to the package deck.",
                )
            ]

        if not _receipt_claim_parity_verified(
            receipt=receipt,
            claim=claim,
            source_evidence_rows=source_evidence_rows,
        ):
            return [
                _source_receipt_reason(
                    "source_receipt_claim_parity_mismatch",
                    "Canonical source receipt source identity differs from its claim.",
                )
            ]
    return []


def _source_authority_state(
    package: Path,
) -> tuple[list[dict[str, str]], int]:
    bundle_path = package / "reports" / "guide_claim_bundle.json"
    if not bundle_path.is_file():
        return [], 0
    try:
        bundle = read_json(bundle_path)
    except (OSError, ValueError):
        return [_source_authority_invalid_reason()], 0
    if not isinstance(bundle, Mapping):
        return [_source_authority_invalid_reason()], 0
    receipts = bundle.get(
        "canonical_source_receipts",
        bundle.get("globalvalues_source_receipts", []),
    )
    if not isinstance(receipts, list):
        return [_source_authority_invalid_reason()], 0
    if not receipts:
        return [], 0
    try:
        deck_identity = read_json(
            package / "reports" / "deck_identity.json"
        )
    except (OSError, ValueError):
        deck_identity = {}
    if not isinstance(deck_identity, Mapping):
        deck_identity = {}
    return (
        canonical_source_receipt_reasons(
            bundle=bundle,
            deck_identity=deck_identity,
        ),
        len(receipts),
    )


def _receipt_claim_parity_verified(
    *,
    receipt: Mapping[str, Any],
    claim: Mapping[str, Any],
    source_evidence_rows: Sequence[Any],
) -> bool:
    source_ref = _clean_text(receipt.get("source_ref"))
    source_url = _clean_text(receipt.get("source_url"))
    claim_source_url = _clean_text(claim.get("source_url"))
    claim_source_refs = claim.get("source_refs", [])
    if isinstance(claim_source_refs, Sequence) and not isinstance(
        claim_source_refs,
        (str, bytes, bytearray),
    ):
        normalized_claim_source_refs = {
            _clean_text(value)
            for value in claim_source_refs
        }
    else:
        normalized_claim_source_refs = set()
    direct_claim_source_ref = _clean_text(claim.get("source_ref"))
    if direct_claim_source_ref:
        normalized_claim_source_refs.add(direct_claim_source_ref)

    matching_source_rows = [
        row
        for row in source_evidence_rows
        if isinstance(row, Mapping)
        and _clean_text(row.get("source_ref")) == source_ref
    ]
    if (
        not source_ref
        or source_ref not in normalized_claim_source_refs
        or not source_url
        or source_url != claim_source_url
        or len(matching_source_rows) != 1
        or _clean_text(matching_source_rows[0].get("source_url"))
        != source_url
    ):
        return False

    claim_provenance = strategic_source_receipt_provenance(claim)
    if claim_provenance is None or receipt.get(
        "acquisition_provenance"
    ) != claim_provenance:
        return False
    evidence_provenance = strategic_source_receipt_provenance(
        matching_source_rows[0]
    )
    if evidence_provenance is None or evidence_provenance != claim_provenance:
        return False

    if "claim_kind" in receipt and _clean_text(
        receipt.get("claim_kind")
    ) != _clean_text(claim.get("claim_kind")):
        return False
    return True


def _claim_deck_fingerprint(claim: Mapping[str, Any]) -> str:
    deck_match = claim.get("deck_match")
    if not isinstance(deck_match, Mapping):
        return ""
    exact_evidence = deck_match.get("exact_deck_evidence")
    if not isinstance(exact_evidence, Mapping):
        return ""
    return _clean_text(exact_evidence.get("matched_deck_fingerprint"))


def _source_authority_invalid_reason() -> dict[str, str]:
    return _source_receipt_reason(
        "source_authority_receipt_invalid",
        "Canonical source receipt container or provenance is invalid.",
    )


def _source_receipt_reason(code: str, detail: str) -> dict[str, str]:
    return {
        "reason": code,
        "code": code,
        "detail": detail,
    }


def _clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def source_apply_eligibility_reasons(
    package_root: str | Path,
) -> list[dict[str, str]]:
    package = Path(package_root)
    bundle_path = package / "reports" / "guide_claim_bundle.json"
    if not bundle_path.is_file():
        return []
    try:
        bundle = read_json(bundle_path)
    except ValueError:
        return [_diagnostic_source_not_apply_eligible_reason()]
    if not isinstance(bundle, Mapping):
        return [_diagnostic_source_not_apply_eligible_reason()]
    for row in _source_provenance_projection(bundle):
        if not strategic_source_provenance_is_verified(
            row.get("acquisition_provenance")
        ):
            return [_diagnostic_source_not_apply_eligible_reason()]
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
    source_authority_reasons_value, canonical_receipt_count = (
        _source_authority_state(package)
    )
    source_apply_reasons = source_apply_eligibility_reasons(package)
    return {
        "strict_validation_passed": strict_validation_passed(
            final_strict_validation_report
        ),
        "deck_input_apply_eligible": not deck_input_apply_eligibility_reasons(
            package
        ),
        "source_authority_verified": not source_authority_reasons_value,
        "canonical_receipt_count": canonical_receipt_count,
        "exact_source_closed": (
            canonical_receipt_count > 0
            and not source_authority_reasons_value
        ),
        "source_apply_eligible": not source_apply_reasons,
        "source_apply_eligibility_reasons": [
            str(row["reason"])
            for row in source_apply_reasons
        ],
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
        if (
            relative_path == "reports/card_behavior_plan_report.json"
            and not path.is_file()
        ):
            inputs[relative_path] = _canonical_json_sha256([])
            continue
        payload = read_json(path)
        if not isinstance(payload, Mapping):
            raise ValueError(f"Authoritative package input must be an object: {path}")
        if relative_path == "reports/input_manifest.json":
            manifest = payload
        if relative_path == "reports/card_behavior_plan_report.json":
            inputs[relative_path] = _canonical_json_sha256(
                linked_runtime_owner_projection(payload)
            )
            continue
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
    inputs["reports/guide_claim_bundle.json#source_provenance"] = (
        _canonical_json_sha256(_source_provenance_projection(guide_bundle))
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


def _linked_runtime_owners(package_root: Path) -> list[dict[str, str]]:
    path = package_root / "reports" / "card_behavior_plan_report.json"
    if not path.is_file():
        return []
    behavior_plan = read_json(path)
    if not isinstance(behavior_plan, Mapping):
        raise ValueError(
            f"Linked runtime owner evidence must be an object: {path}"
        )
    return linked_runtime_owner_projection(behavior_plan)


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


def _source_provenance_projection(
    bundle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    projection: list[dict[str, Any]] = []
    for record_kind, rows, id_keys in (
        ("claim", bundle.get("claims", []), ("claim_id", "source_ref")),
        (
            "source_evidence",
            bundle.get("source_evidence_index", []),
            ("source_ref", "source_id"),
        ),
    ):
        if not isinstance(rows, Sequence) or isinstance(
            rows, (str, bytes, bytearray)
        ):
            continue
        for row in rows:
            if not isinstance(row, Mapping) or "acquisition_provenance" not in row:
                continue
            projection.append(
                {
                    "record_kind": record_kind,
                    "record_ids": {
                        key: str(row.get(key, ""))
                        for key in id_keys
                    },
                    "acquisition_provenance": _stable_authority_value(
                        row.get("acquisition_provenance")
                    ),
                }
            )
    return sorted(projection, key=_canonical_json_bytes)


def _diagnostic_source_not_apply_eligible_reason() -> dict[str, str]:
    return {
        "reason": "diagnostic_source_not_apply_eligible",
        "code": "diagnostic_source_not_apply_eligible",
        "detail": (
            "Package source provenance is diagnostic-only and cannot authorize "
            "runtime apply."
        ),
    }


def _canonical_json_sha256(value: Any) -> str:
    return f"sha256:{hashlib.sha256(_canonical_json_bytes(value)).hexdigest()}"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
