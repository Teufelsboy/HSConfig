from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from hsconfig.configuration_mode import (
    LLM_OPTIMIZED_START,
    configuration_mode_from_manifest,
    optimized_start_authority_schema_from_manifest,
)
from hsconfig.io import decode_json_bytes
from hsconfig.package_io import (
    read_optional_profile,
    read_required_baseline,
    read_required_globalvalues_authority_matrix,
)
from hsconfig.package_model import DirectoryPackageView, PackageView
from hsconfig.pre_run_metrics import (
    PRE_RUN_REPORT_PATHS,
    _load_verified_emission_input,
    _metric_ratio_from_document,
    _report_content_sha256,
    _validate_deck_identity,
    _verified_emission_expectations_for_mode,
    _verified_emission_from_package_view,
    eligible_emission_recall,
    emission_precision,
    load_disposition_ledger_report,
    load_globalvalues_decision_ledger_report,
    source_acquisition_input_binding,
    validate_pre_run_package_reports,
)
from hsconfig.input_snapshot_manifest import (
    INPUT_SNAPSHOT_FIELDS,
    INPUT_SNAPSHOT_MAX_BYTES,
    INPUT_SNAPSHOT_SCHEMA_VERSION,
    validate_input_snapshot_manifest_document,
)
from hsconfig.optimized_start_authority import (
    ValidatedOptimizedStartAuthority,
    ValidatedSingleStarterApproval,
    load_optimized_start_authority,
)
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.runtime_entity_owner import (
    AUTHORIZED_HERO_POWER_OWNER,
    LINKED_RUNTIME_ENTITY_RELATION_INVALID,
    linked_runtime_entity_semantic_surface,
    runtime_entity_owner_relation_is_authorized,
)
from hsconfig.runtime_surface_ledger import (
    rederive_runtime_surface_ledger_from_package,
    rederive_runtime_surface_ledger_from_view,
)
from hsconfig.strict_run_validation import verify_configure_run_package
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import validate_starter_context_document
from hsconfig.starter_contract import (
    QUALITY_STARTER_CONTEXT_FIELDS,
    QUALITY_STARTER_CANDIDATE_FIELDS,
    QUALITY_STARTER_REVIEW_FIELDS,
    QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
    live_contract_for_versions,
    SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
    SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
    STARTER_CANDIDATE_FILENAMES,
    STARTER_CANDIDATE_FIELDS,
    STARTER_CANDIDATE_MAX_BYTES,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_FILENAME,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_DECISION_FIELDS,
    STARTER_DECISION_FILENAME,
    STARTER_DECISION_MAX_BYTES,
    STARTER_REVIEW_FIELDS,
    STARTER_REVIEW_MAX_BYTES,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_decision import (
    ValidatedStarterSelection,
    _validate_candidate_set,
    _validate_decision,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document
from hsconfig.starter_review import validate_starter_review
from hsconfig.validate_package import (
    _reject_nonstandard_json_constant,
    _validate_blocks,
    _validate_top_level,
    optimized_start_authority_report_set_errors,
    validate_legacy_starter_candidate_path_mapping,
    validate_config_package,
)
from hsconfig.visionai_registry import (
    REQUIRED_RUNTIME_SURFACES,
    supported_surface,
)


LINKED_RUNTIME_OWNER_EVIDENCE_MISSING = (
    "linked_runtime_owner_evidence_missing"
)
LINKED_RUNTIME_OWNER_EVIDENCE_INVALID = (
    "linked_runtime_owner_evidence_invalid"
)
def strict_validation_passed(report: dict[str, Any]) -> bool:
    return report.get("status") == "passed" and not report.get("errors")


def validate_complete_configure_run_from_view(
    revision: PackageView,
) -> dict[str, Any]:
    """Verify a full run before validating its snapshotted package subtree."""

    try:
        _manifest, package = verify_configure_run_package(revision)
    except ValueError:
        return {
            "status": "failed",
            "errors": ["run_manifest_invalid"],
            "checked_files": 0,
        }
    try:
        return validate_complete_package_from_view(package)
    except Exception:
        return {
            "status": "failed",
            "errors": ["package_validation_invalid"],
            "checked_files": 0,
        }


def validate_complete_package(
    package: str | Path,
    *,
    allow_legacy_globalvalues: bool = False,
    legacy_pre_run_contract_version: int | None = None,
) -> dict[str, Any]:
    """Run the strict complete-package contract used by every caller."""
    package_path = Path(package)
    try:
        configuration_mode, optimized_globalvalues_ledger = (
            _globalvalues_authority_from_view(
                DirectoryPackageView(package_path)
            )
        )
    except (OSError, TypeError, ValueError):
        return {
            "status": "failed",
            "errors": ["configuration_mode_invalid"],
            "checked_files": 0,
        }
    baseline = read_required_baseline(package_path)
    profile = read_optional_profile(package_path)
    authority_matrix_path = (
        package_path / "reports" / "global_values_authority_matrix.json"
    )
    authority_matrix = (
        read_required_globalvalues_authority_matrix(package_path)
        if authority_matrix_path.is_file()
        else None
    )
    report = validate_config_package(
        package_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        globalvalues_authority_matrix=authority_matrix,
        configuration_mode=configuration_mode,
        optimized_globalvalues_decision_ledger=(
            optimized_globalvalues_ledger
        ),
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    linked_runtime_errors = _validate_linked_runtime_entities(package_path)
    physical_surface_errors = _validate_runtime_surface_ledger(package_path)
    pre_run_contract_errors = _validate_pre_run_contract_reports(
        package_path,
        legacy_contract_version=legacy_pre_run_contract_version,
    )
    optimized_start_report_errors = _validate_optimized_start_reports(
        package_path
    )
    report_errors = report.get("errors", [])
    optimized_start_report_errors = [
        error
        for error in optimized_start_report_errors
        if error not in report_errors
    ]
    globalvalues_contract_errors = []
    if authority_matrix is None and not allow_legacy_globalvalues:
        globalvalues_contract_errors.append(
            "GlobalValues current contract requires authority matrix "
            "reports/global_values_authority_matrix.json"
        )
    if (
        not linked_runtime_errors
        and not physical_surface_errors
        and not globalvalues_contract_errors
        and not pre_run_contract_errors
        and not optimized_start_report_errors
    ):
        return report
    return {
        **report,
        "status": "failed",
        "errors": [
            *report.get("errors", []),
            *globalvalues_contract_errors,
            *linked_runtime_errors,
            *physical_surface_errors,
            *pre_run_contract_errors,
            *optimized_start_report_errors,
        ],
    }


def validate_complete_package_from_view(
    package: PackageView,
    *,
    allow_legacy_globalvalues: bool = False,
    legacy_pre_run_contract_version: int | None = None,
) -> dict[str, Any]:
    """Run the strict complete-package contract without filesystem adaptation."""

    try:
        configuration_mode, optimized_globalvalues_ledger = (
            _globalvalues_authority_from_view(package)
        )
    except (OSError, TypeError, ValueError):
        return {
            "status": "failed",
            "errors": ["configuration_mode_invalid"],
            "checked_files": 0,
        }
    baseline = _required_view_mapping(
        package,
        "reports/globalvalues_baseline.json",
        "GlobalValues baseline",
    )
    profile = _optional_view_mapping(
        package,
        "reports/globalvalues_profile.json",
        "GlobalValues profile",
    )
    authority_matrix = _optional_view_mapping(
        package,
        "reports/global_values_authority_matrix.json",
        "GlobalValues authority matrix",
    )
    report = _validate_config_package_view(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        globalvalues_authority_matrix=authority_matrix,
        configuration_mode=configuration_mode,
        optimized_globalvalues_decision_ledger=(
            optimized_globalvalues_ledger
        ),
    )
    linked_runtime_errors = _validate_linked_runtime_entities_view(package)
    physical_surface_errors = _validate_runtime_surface_ledger_view(package)
    pre_run_contract_errors = _validate_pre_run_contract_reports_view(
        package,
        legacy_contract_version=legacy_pre_run_contract_version,
    )
    optimized_start_report_errors = _validate_optimized_start_reports_view(
        package
    )
    globalvalues_contract_errors = []
    if authority_matrix is None and not allow_legacy_globalvalues:
        globalvalues_contract_errors.append(
            "GlobalValues current contract requires authority matrix "
            "reports/global_values_authority_matrix.json"
        )
    if (
        not linked_runtime_errors
        and not physical_surface_errors
        and not globalvalues_contract_errors
        and not pre_run_contract_errors
        and not optimized_start_report_errors
    ):
        return report
    return {
        **report,
        "status": "failed",
        "errors": [
            *report.get("errors", []),
            *globalvalues_contract_errors,
            *linked_runtime_errors,
            *physical_surface_errors,
            *pre_run_contract_errors,
            *optimized_start_report_errors,
        ],
    }


def _validate_optimized_start_reports(package: Path) -> list[str]:
    manifest_path = package / "reports" / "input_manifest.json"
    try:
        manifest = decode_json_bytes(manifest_path.read_bytes())
        configuration_mode = configuration_mode_from_manifest(manifest)
    except (OSError, TypeError, ValueError):
        return ["configuration_mode_invalid"]
    view = DirectoryPackageView(package)
    errors = optimized_start_authority_report_set_errors(
        file_names=view.file_names(),
        manifest=manifest,
    )
    if errors or configuration_mode != LLM_OPTIMIZED_START:
        return errors
    try:
        authority = load_optimized_start_authority(
            report_root=package / "reports" / "optimized_start",
            manifest=manifest,
        )
        if isinstance(authority, ValidatedStarterSelection):
            validate_legacy_starter_candidate_path_mapping(
                authority.candidates
            )
    except (KeyError, OSError, TypeError, ValueError):
        return ["optimized_start_authority_invalid"]
    return []


def _validate_optimized_start_reports_view(
    package: PackageView,
) -> list[str]:
    try:
        manifest = decode_json_bytes(
            package.read_bytes("reports/input_manifest.json")
        )
        configuration_mode = configuration_mode_from_manifest(manifest)
    except (OSError, TypeError, ValueError):
        return ["configuration_mode_invalid"]
    errors = optimized_start_authority_report_set_errors(
        file_names=package.file_names(),
        manifest=manifest,
    )
    if errors or configuration_mode != LLM_OPTIMIZED_START:
        return errors
    try:
        validated_optimized_start_authority_from_view(
            package,
            manifest=manifest,
        )
    except (KeyError, OSError, TypeError, ValueError):
        return ["optimized_start_authority_invalid"]
    return []


def validated_optimized_start_authority_from_view(
    package: PackageView,
    *,
    manifest: Mapping[str, Any],
) -> ValidatedOptimizedStartAuthority:
    """Validate one exact optimized authority from an immutable package view."""

    errors = optimized_start_authority_report_set_errors(
        file_names=package.file_names(),
        manifest=manifest,
    )
    if errors:
        raise ValueError(errors[0])
    schema = optimized_start_authority_schema_from_manifest(manifest)
    if schema == "legacy_five_doc":
        return _legacy_optimized_start_authority_from_view(package)
    if schema in {"single_candidate_review_v1", "single_candidate_review_v2"}:
        return _single_candidate_review_authority_from_view(package)
    raise ValueError("optimized_start_authority_not_enabled")


def _legacy_optimized_start_authority_from_view(
    package: PackageView,
) -> ValidatedStarterSelection:
    root = "reports/optimized_start"
    context = validate_starter_context_document(
        _starter_document_from_view(
            package,
            f"{root}/{STARTER_CONTEXT_FILENAME}",
            maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
            expected_fields=STARTER_CONTEXT_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
    )
    candidates = tuple(
        validate_starter_candidate(
            _starter_document_from_view(
                package,
                f"{root}/{filename}",
                maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
                expected_fields=STARTER_CANDIDATE_FIELDS,
                schema_version=STARTER_SCHEMA_VERSION,
            ),
            context=context,
        )
        for filename in STARTER_CANDIDATE_FILENAMES
    )
    _validate_candidate_set(candidates)
    validate_legacy_starter_candidate_path_mapping(candidates)
    decision = _starter_document_from_view(
        package,
        f"{root}/{STARTER_DECISION_FILENAME}",
        maximum_bytes=STARTER_DECISION_MAX_BYTES,
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    selected_id = _validate_decision(
        decision,
        current_context=context,
        candidates=candidates,
    )
    selected = next(
        candidate
        for candidate in candidates
        if candidate.candidate_id == selected_id
    )
    return ValidatedStarterSelection(
        context=context,
        candidates=candidates,
        decision=decision,
        selected=selected,
    )


def _single_candidate_review_authority_from_view(
    package: PackageView,
) -> ValidatedSingleStarterApproval:
    root = "reports/optimized_start"
    schema = optimized_start_authority_schema_from_manifest(
        package.read_json("reports/input_manifest.json")
    )
    if schema not in {"single_candidate_review_v1", "single_candidate_review_v2"}:
        raise ValueError("optimized_start_authority_schema_invalid")
    quality = schema == "single_candidate_review_v2"
    version = 3 if quality else 2
    snapshot_document = _starter_document_from_view(
        package,
        f"{root}/input_snapshot_manifest.json",
        maximum_bytes=INPUT_SNAPSHOT_MAX_BYTES,
        expected_fields=INPUT_SNAPSHOT_FIELDS,
        schema_version=2 if quality else INPUT_SNAPSHOT_SCHEMA_VERSION,
    )
    snapshot = validate_input_snapshot_manifest_document(
        snapshot_document.document
    )
    live_contract_for_versions(
        session=2 if quality else 1,
        manifest=snapshot.document.to_value()["schema_version"],
        context=version,
        candidate=version,
        review=version,
        compiler=snapshot.compiler_inputs.to_value()["compiler_contract_id"],
    )
    context = validate_starter_context_document(
        _starter_document_from_view(
            package,
            f"{root}/{STARTER_CONTEXT_FILENAME}",
            maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
            expected_fields=QUALITY_STARTER_CONTEXT_FIELDS
            if quality
            else SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
            schema_version=version,
        )
    )
    candidate = validate_starter_candidate(
        _starter_document_from_view(
            package,
            f"{root}/starter_config_candidate.json",
            maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
            expected_fields=QUALITY_STARTER_CANDIDATE_FIELDS
            if quality
            else SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
            schema_version=version,
        ),
        context=context,
    )
    receipt = (
        _starter_document_from_view(
            package,
            f"{root}/candidate_validation_receipt.json",
            maximum_bytes=512 * 1024,
            expected_fields=QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
            schema_version=2,
        ).document
        if quality
        else None
    )
    review = validate_starter_review(
        _starter_document_from_view(
            package,
            f"{root}/starter_config_review.json",
            maximum_bytes=STARTER_REVIEW_MAX_BYTES,
            expected_fields=QUALITY_STARTER_REVIEW_FIELDS
            if quality
            else STARTER_REVIEW_FIELDS,
            schema_version=version,
        ),
        context=context,
        candidate=candidate,
        validation_receipt=receipt,
    )
    if not (
        context.document.to_value()["input_snapshot_manifest_sha256"]
        == snapshot.document.content_sha256
        and candidate.candidate_id == "lead"
        and review.candidate_id == candidate.candidate_id
        and review.candidate_revision == candidate.candidate_revision
        and review.candidate_sha256 == candidate.document.content_sha256
        and review.review_status == "approved"
        and review.revision_requests == ()
        and review.confidence in {"high", "limited"}
    ):
        raise ValueError("single_starter_approval_invalid")
    return ValidatedSingleStarterApproval(
        snapshot=snapshot,
        context=context,
        candidate=candidate,
        review=review,
        validation_receipt=receipt,
    )


def _starter_document_from_view(
    package: PackageView,
    relative_path: str,
    *,
    maximum_bytes: int,
    expected_fields: frozenset[str],
    schema_version: int,
) -> StarterDocument:
    raw_value = package.read_bytes(relative_path)
    if not isinstance(raw_value, (bytes, bytearray, memoryview)):
        raise TypeError("starter_document_bytes_invalid")
    raw = memoryview(raw_value).tobytes()
    if len(raw) > maximum_bytes:
        raise ValueError("starter_document_too_large")
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw or b"\r" in raw:
        raise ValueError("starter_document_source_bytes_invalid")
    frozen = FrozenJsonDocument.from_json_bytes(raw)
    if frozen.canonical_json != raw:
        raise ValueError("starter_document_not_canonical")
    value = frozen.to_value()
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise ValueError("starter_document_fields_invalid")
    unsigned = dict(value)
    content_sha256 = unsigned.pop("content_sha256")
    sealed = seal_starter_document(
        unsigned,
        expected_fields=expected_fields,
        schema_version=schema_version,
    )
    if (
        sealed.canonical_json != raw
        or sealed.content_sha256 != content_sha256
    ):
        raise ValueError("starter_document_content_sha256_invalid")
    return sealed


def _validate_config_package_view(
    package: PackageView,
    *,
    globalvalues_baseline: dict[str, Any],
    globalvalues_profile: dict[str, Any] | None,
    globalvalues_authority_matrix: dict[str, Any] | None,
    configuration_mode: str,
    optimized_globalvalues_decision_ledger: dict[str, Any] | None,
) -> dict[str, Any]:
    errors: list[str] = []
    checked_files = 0
    direct_paths = tuple(
        sorted(
            name
            for name in package.file_names()
            if name.startswith("CustomConfig/")
            and len(name.split("/")) == 3
        )
    )
    deck_names = tuple(sorted({name.split("/")[1] for name in direct_paths}))
    if not deck_names:
        errors.append("memory:/CustomConfig: no deck config directories found")
    elif len(deck_names) > 1:
        errors.append(
            "memory:/CustomConfig: expected exactly one deck config directory "
            f"for complete package, found {len(deck_names)}: "
            f"{', '.join(deck_names)}"
        )
    for deck_name in deck_names:
        file_names = tuple(
            sorted(
                name.rsplit("/", 1)[-1]
                for name in direct_paths
                if name.split("/")[1] == deck_name
            )
        )
        for required in sorted(REQUIRED_RUNTIME_SURFACES):
            if required not in file_names:
                errors.append(
                    f"memory:/CustomConfig/{deck_name}: "
                    f"missing required runtime file {required}"
                )
        for relative_path in (
            name
            for name in direct_paths
            if name.split("/")[1] == deck_name
        ):
            path = Path("memory:") / relative_path
            if not supported_surface(path.name):
                errors.append(f"{path}: unsupported VisionAI surface")
                continue
            checked_files += 1
            try:
                data = json.loads(
                    package.read_bytes(relative_path).decode("utf-8-sig"),
                    parse_constant=_reject_nonstandard_json_constant,
                )
            except Exception as exc:
                errors.append(f"{path}: invalid JSON: {exc}")
                continue
            if not isinstance(data, dict):
                errors.append(
                    f"{path}: top-level JSON value must be an object"
                )
                continue
            errors.extend(_validate_top_level(path, data))
            errors.extend(
                _validate_blocks(
                    path,
                    data,
                    globalvalues_baseline=globalvalues_baseline,
                    globalvalues_profile=globalvalues_profile,
                    globalvalues_authority_matrix=(
                        globalvalues_authority_matrix
                    ),
                    configuration_mode=configuration_mode,
                    optimized_globalvalues_decision_ledger=(
                        optimized_globalvalues_decision_ledger
                    ),
                    require_globalvalues_profile=True,
                )
            )
        if globalvalues_profile is None:
            errors.append(
                f"memory:/CustomConfig/{deck_name}: "
                "missing required GlobalValues profile"
            )
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "checked_files": checked_files,
    }


def _globalvalues_authority_from_view(
    package: PackageView,
) -> tuple[str, dict[str, Any] | None]:
    manifest = _required_view_mapping(
        package,
        "reports/input_manifest.json",
        "input manifest",
    )
    configuration_mode = configuration_mode_from_manifest(manifest)
    if configuration_mode != LLM_OPTIMIZED_START:
        return configuration_mode, None
    ledger = _required_view_mapping(
        package,
        "reports/globalvalues_decision_ledger.json",
        "optimized GlobalValues decision ledger",
    )
    return configuration_mode, ledger


def _validate_pre_run_contract_reports(
    package_path: Path,
    *,
    legacy_contract_version: int | None,
) -> list[str]:
    view = DirectoryPackageView(package_path)
    if not any(view.exists(path) for path in PRE_RUN_REPORT_PATHS):
        marker = None
        if view.exists("reports/input_manifest.json"):
            try:
                manifest = view.read_json("reports/input_manifest.json")
            except (OSError, UnicodeDecodeError, ValueError):
                manifest = None
            if isinstance(manifest, Mapping):
                marker = manifest.get(
                    "pre_run_contract_schema_version"
                )
        if legacy_contract_version == 0 and marker is None:
            return []
        return [
            "pre_run_contract_validation_failed:"
            "pre_run_current_reports_missing"
        ]
    try:
        manifest = view.read_json("reports/input_manifest.json")
        if (
            isinstance(manifest, Mapping)
            and optimized_start_authority_schema_from_manifest(manifest)
            == "single_candidate_review_v1"
        ):
            _validate_single_candidate_pre_run_reports(view)
        else:
            validate_pre_run_package_reports(view)
    except (OSError, TypeError, ValueError) as error:
        return [f"pre_run_contract_validation_failed:{error}"]
    return []


def _validate_pre_run_contract_reports_view(
    package: PackageView,
    *,
    legacy_contract_version: int | None,
) -> list[str]:
    if not any(package.exists(path) for path in PRE_RUN_REPORT_PATHS):
        marker = None
        if package.exists("reports/input_manifest.json"):
            try:
                manifest = package.read_json(
                    "reports/input_manifest.json"
                )
            except (OSError, UnicodeDecodeError, ValueError):
                manifest = None
            if isinstance(manifest, Mapping):
                marker = manifest.get("pre_run_contract_schema_version")
        if legacy_contract_version == 0 and marker is None:
            return []
        return [
            "pre_run_contract_validation_failed:"
            "pre_run_current_reports_missing"
        ]
    try:
        manifest = package.read_json("reports/input_manifest.json")
        if (
            isinstance(manifest, Mapping)
            and optimized_start_authority_schema_from_manifest(manifest)
            == "single_candidate_review_v1"
        ):
            _validate_single_candidate_pre_run_reports(package)
        else:
            validate_pre_run_package_reports(package)
    except (OSError, TypeError, ValueError) as error:
        return [f"pre_run_contract_validation_failed:{error}"]
    return []


def _validate_single_candidate_pre_run_reports(
    package: PackageView,
) -> None:
    """Validate V2 diagnostics without granting unfrozen policy authority."""

    try:
        validate_pre_run_package_reports(package)
    except ValueError as error:
        if str(error) != "source_acquisition_policy_binding_mismatch":
            raise
    else:
        raise ValueError("source_acquisition_policy_binding_unexpected")

    documents = {
        path: package.read_json(path) for path in PRE_RUN_REPORT_PATHS
    }
    deck_identity = package.read_json("reports/deck_identity.json")
    input_manifest = package.read_json("reports/input_manifest.json")
    source_contract_audit = (
        package.read_json("reports/source_contract_audit.json")
        if package.exists("reports/source_contract_audit.json")
        else None
    )
    if (
        not isinstance(deck_identity, Mapping)
        or not isinstance(input_manifest, Mapping)
        or any(
            not isinstance(document, Mapping)
            for document in documents.values()
        )
        or (
            source_contract_audit is not None
            and not isinstance(source_contract_audit, Mapping)
        )
    ):
        raise ValueError("pre_run_report_malformed")
    disposition = load_disposition_ledger_report(
        documents["reports/disposition_ledger.json"]
    )
    globalvalues = load_globalvalues_decision_ledger_report(
        documents["reports/globalvalues_decision_ledger.json"]
    )
    fingerprint = disposition.deck_fingerprint
    if globalvalues.deck_fingerprint != fingerprint:
        raise ValueError("pre_run_report_cross_deck")
    acquisition = documents["reports/source_acquisition_closure.json"]
    _validate_not_frozen_acquisition_diagnostic(
        acquisition,
        deck_fingerprint=fingerprint,
    )
    if input_manifest.get(
        "source_acquisition_input_binding"
    ) != source_acquisition_input_binding(acquisition):
        raise ValueError("source_acquisition_upstream_manifest_mismatch")

    pre_run = documents["reports/pre_run_closure.json"]
    if pre_run.get("content_sha256") != _report_content_sha256(pre_run):
        raise ValueError("pre_run_closure_hash_stale")
    if (
        pre_run.get("deck_fingerprint") != fingerprint
        or deck_identity.get("deck_fingerprint") != fingerprint
    ):
        raise ValueError("pre_run_report_cross_deck")
    _validate_deck_identity(deck_identity, fingerprint=fingerprint)
    expected_hashes = {
        "layered_evidence_contract": documents[
            "reports/layered_evidence_contract.json"
        ]["content_sha256"],
        "source_acquisition_closure": acquisition["content_sha256"],
        "disposition_ledger": disposition.content_sha256,
        "globalvalues_decision_ledger": globalvalues.content_sha256,
    }
    if pre_run.get("report_hashes") != expected_hashes:
        raise ValueError("pre_run_closure_report_hash_mismatch")
    expected_counts = {
        "card_disposition_count": len(disposition.cards),
        "final_card_disposition_count": len(disposition.cards),
        "claim_count": len(disposition.claims),
        "final_claim_disposition_count": len(disposition.claims),
        "globalvalues_decision_count": len(globalvalues.decisions),
        "final_globalvalues_decision_count": len(globalvalues.decisions),
    }
    if pre_run.get("counts") != expected_counts:
        raise ValueError("pre_run_closure_totals_mismatch")

    verified = _load_verified_emission_input(
        pre_run.get("verified_emission")
    )
    if verified.deck_fingerprint != fingerprint:
        raise ValueError("verified_emission_cross_deck")
    expected_semantics = _verified_emission_expectations_for_mode(
        configuration_mode=LLM_OPTIMIZED_START,
        disposition_ledger=disposition,
        source_contract_audit=source_contract_audit,
    )
    if verified.expectations != expected_semantics:
        raise ValueError("verified_emission_semantic_projection_mismatch")
    if package.exists("reports/runtime_surface_ledger.json"):
        rederived_verified = _verified_emission_from_package_view(
            package=package,
            disposition_ledger=disposition,
            source_contract_audit=source_contract_audit,
            configuration_mode=LLM_OPTIMIZED_START,
        )
        if verified != rederived_verified:
            raise ValueError("verified_emission_package_view_mismatch")
    elif verified.physical_rows:
        raise ValueError("verified_emission_package_view_mismatch")
    precision = emission_precision(verified)
    recall = eligible_emission_recall(verified)
    if pre_run.get("emission_precision") != precision.to_document():
        raise ValueError("pre_run_emission_precision_mismatch")
    if pre_run.get("eligible_emission_recall") != recall.to_document():
        raise ValueError("pre_run_emission_recall_mismatch")
    layered = _metric_ratio_from_document(
        pre_run.get("layered_pre_run_source_coverage")
    )
    report_layered = _metric_ratio_from_document(
        documents["reports/layered_evidence_contract.json"].get(
            "layered_coverage"
        )
    )
    if layered != report_layered:
        raise ValueError("pre_run_layered_coverage_mismatch")
    if pre_run.get("pre_run_contract_status") != "incomplete":
        raise ValueError("pre_run_closure_status_mismatch")
    strategy = pre_run.get("strategy_authority_status")
    if strategy not in {"partial", "strong"}:
        raise ValueError("pre_run_strategy_authority_status_invalid")
    exact = documents["reports/layered_evidence_contract.json"].get(
        "exact_guide_authority"
    ) is True
    if pre_run.get("exact_guide_authority") is not exact:
        raise ValueError("pre_run_exact_guide_authority_mismatch")
    for field, expected in (
        ("hsconfig_scope", "PRE_RUN_CONTRACT"),
        ("gameplay_strategy_owner", "hearthranger_bot"),
        ("gameplay_quality", "OUT_OF_SCOPE_ASSUMED_EXTERNAL"),
        ("bot_gameplay_assumption", "trusted_external"),
    ):
        if pre_run.get(field) != expected:
            raise ValueError(f"pre_run_closure_{field}_invalid")


def _validate_not_frozen_acquisition_diagnostic(
    document: Mapping[str, Any],
    *,
    deck_fingerprint: str,
) -> None:
    expected_fields = {
        "schema_version",
        "authority",
        "operator_gate_impact",
        "apply_blocking",
        "normal_apply_authority",
        "deck_fingerprint",
        "source_acquisition_complete",
        "policy_provenance",
        "acquisition_closure",
        "content_sha256",
    }
    if (
        set(document) != expected_fields
        or document.get("content_sha256")
        != _report_content_sha256(document)
        or document.get("schema_version") != 1
        or document.get("authority") != "diagnostic_only"
        or document.get("operator_gate_impact") != "diagnostic_only"
        or document.get("apply_blocking") is not False
        or document.get("normal_apply_authority")
        != "reports/operator_summary.json"
        or document.get("deck_fingerprint") != deck_fingerprint
        or document.get("source_acquisition_complete") is not False
        or document.get("policy_provenance")
        != {"runtime_authorized": False, "status": "not_frozen"}
    ):
        raise ValueError("source_acquisition_not_frozen_invalid")
    closure = document.get("acquisition_closure")
    expected_closure = {
        "deck_fingerprint": deck_fingerprint,
        "attempt_id": "",
        "attempted_at": "",
        "attempted_urls": [],
        "successful_evidence_ids": [],
        "failed_attempts": [],
        "negative_search_documented": False,
        "checked_dossier": False,
        "policy_id": None,
        "status": "open",
        "content_sha256": "sha256:" + ("0" * 64),
    }
    if closure != expected_closure:
        raise ValueError("source_acquisition_not_frozen_invalid")


def _validate_runtime_surface_ledger(package_path: Path) -> list[str]:
    """Validate the serialized schema-2 ledger against physical package files."""
    path = package_path / "reports" / "runtime_surface_ledger.json"
    if not path.is_file():
        return ["runtime_surface_ledger_missing"]
    try:
        ledger = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return ["runtime_surface_ledger_invalid"]
    if not isinstance(ledger, Mapping):
        return ["runtime_surface_ledger_invalid"]

    if (
        type(ledger.get("schema_version")) is not int
        or ledger.get("schema_version") != 2
    ):
        return ["runtime_surface_ledger_schema_invalid"]
    try:
        rederived = rederive_runtime_surface_ledger_from_package(package_path)
    except (OSError, ValueError, TypeError):
        return ["runtime_surface_ledger_rederive_failed"]

    errors: list[str] = []
    if ledger.get("surface_ledger_sha256") != rederived.get("surface_ledger_sha256"):
        errors.append("runtime_surface_ledger_sha256_mismatch")
    if _canonical_json(ledger) != _canonical_json(rederived):
        errors.append("runtime_surface_ledger_content_mismatch")

    for value in rederived.get("physical_errors", []):
        errors.append(f"runtime_surface_ledger_physical_error:{value}")
    for row in rederived.get("unexpected_runtime_emissions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_unexpected_emission:"
                f"{row.get('card_id', '')}:{row.get('reason', '')}"
            )
        else:
            errors.append("runtime_surface_ledger_unexpected_emission:invalid")
    for row in rederived.get("linked_runtime_owner_collisions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_owner_collision:"
                f"{row.get('runtime_card_id', '')}"
            )
        else:
            errors.append("runtime_surface_ledger_owner_collision:invalid")
    return sorted(set(errors))


def _validate_runtime_surface_ledger_view(
    package: PackageView,
) -> list[str]:
    path = "reports/runtime_surface_ledger.json"
    if not package.exists(path):
        return ["runtime_surface_ledger_missing"]
    try:
        ledger = decode_json_bytes(package.read_bytes(path))
    except (OSError, ValueError):
        return ["runtime_surface_ledger_invalid"]
    if not isinstance(ledger, Mapping):
        return ["runtime_surface_ledger_invalid"]
    if (
        type(ledger.get("schema_version")) is not int
        or ledger.get("schema_version") != 2
    ):
        return ["runtime_surface_ledger_schema_invalid"]
    try:
        rederived = rederive_runtime_surface_ledger_from_view(package)
    except (OSError, ValueError, TypeError):
        return ["runtime_surface_ledger_rederive_failed"]
    return _runtime_surface_ledger_errors(ledger, rederived)


def _runtime_surface_ledger_errors(
    ledger: Mapping[str, Any],
    rederived: Mapping[str, Any],
) -> list[str]:
    errors: list[str] = []
    if (
        ledger.get("surface_ledger_sha256")
        != rederived.get("surface_ledger_sha256")
    ):
        errors.append("runtime_surface_ledger_sha256_mismatch")
    if _canonical_json(ledger) != _canonical_json(rederived):
        errors.append("runtime_surface_ledger_content_mismatch")
    for value in rederived.get("physical_errors", []):
        errors.append(f"runtime_surface_ledger_physical_error:{value}")
    for row in rederived.get("unexpected_runtime_emissions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_unexpected_emission:"
                f"{row.get('card_id', '')}:{row.get('reason', '')}"
            )
        else:
            errors.append(
                "runtime_surface_ledger_unexpected_emission:invalid"
            )
    for row in rederived.get("linked_runtime_owner_collisions", []):
        if isinstance(row, Mapping):
            errors.append(
                "runtime_surface_ledger_owner_collision:"
                f"{row.get('runtime_card_id', '')}"
            )
        else:
            errors.append("runtime_surface_ledger_owner_collision:invalid")
    return sorted(set(errors))


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _required_view_mapping(
    package: PackageView,
    relative_path: str,
    label: str,
) -> dict[str, Any]:
    if not package.exists(relative_path):
        raise ValueError(f"Missing {label} report: {relative_path}")
    value = decode_json_bytes(package.read_bytes(relative_path))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object: {relative_path}")
    return value


def _optional_view_mapping(
    package: PackageView,
    relative_path: str,
    label: str,
) -> dict[str, Any] | None:
    if not package.exists(relative_path):
        return None
    value = decode_json_bytes(package.read_bytes(relative_path))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object: {relative_path}")
    return value


def _validate_linked_runtime_entities(package_path: Path) -> list[str]:
    behavior_plan_path = (
        package_path / "reports" / "card_behavior_plan_report.json"
    )
    if not behavior_plan_path.is_file():
        if _has_curated_linked_runtime_owner_file(package_path):
            return [LINKED_RUNTIME_OWNER_EVIDENCE_MISSING]
        return []
    try:
        behavior_plan = json.loads(
            behavior_plan_path.read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError):
        return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
    if not isinstance(behavior_plan, Mapping):
        return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]

    has_curated_owner = _has_curated_linked_runtime_owner_file(package_path)

    deck_dirs = sorted(
        path
        for path in (package_path / "CustomConfig").glob("*")
        if path.is_dir()
    )
    errors: list[str] = []
    try:
        linked_relations, relation_errors = _linked_runtime_relations(
            behavior_plan
        )
    except ValueError as error:
        if str(error) == LINKED_RUNTIME_OWNER_EVIDENCE_INVALID:
            return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
        raise
    errors.extend(relation_errors)
    if has_curated_owner and not _has_curated_linked_runtime_owner_relation(
        linked_relations
    ):
        errors.append(LINKED_RUNTIME_OWNER_EVIDENCE_MISSING)
    for relation in linked_relations:
        runtime_card_id = relation["runtime_card_id"]
        filename = f"{runtime_card_id}.json"
        matching_paths = [
            deck_dir / filename
            for deck_dir in deck_dirs
            if (deck_dir / filename).is_file()
        ]
        if not matching_paths:
            errors.append(
                "linked runtime entity missing required owner file: "
                f"{filename}"
            )
            continue
        for path in matching_paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            actual = payload.get("GameCardId")
            if actual != runtime_card_id:
                errors.append(
                    "linked runtime entity filename/GameCardId mismatch: "
                    f"{filename} owns {runtime_card_id}, got {actual}"
                )
    return errors


def _validate_linked_runtime_entities_view(
    package: PackageView,
) -> list[str]:
    behavior_path = "reports/card_behavior_plan_report.json"
    if not package.exists(behavior_path):
        if _has_curated_linked_runtime_owner_file_view(package):
            return [LINKED_RUNTIME_OWNER_EVIDENCE_MISSING]
        return []
    try:
        behavior_plan = decode_json_bytes(package.read_bytes(behavior_path))
    except (OSError, ValueError):
        return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
    if not isinstance(behavior_plan, Mapping):
        return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
    has_curated_owner = _has_curated_linked_runtime_owner_file_view(
        package
    )
    errors: list[str] = []
    try:
        linked_relations, relation_errors = _linked_runtime_relations(
            behavior_plan
        )
    except ValueError as error:
        if str(error) == LINKED_RUNTIME_OWNER_EVIDENCE_INVALID:
            return [LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]
        raise
    errors.extend(relation_errors)
    if has_curated_owner and not _has_curated_linked_runtime_owner_relation(
        linked_relations
    ):
        errors.append(LINKED_RUNTIME_OWNER_EVIDENCE_MISSING)
    runtime_names = set(package.file_names())
    for relation in linked_relations:
        runtime_card_id = relation["runtime_card_id"]
        filename = f"{runtime_card_id}.json"
        matching_paths = sorted(
            name
            for name in runtime_names
            if name.startswith("CustomConfig/")
            and name.endswith(f"/{filename}")
            and len(name.split("/")) == 3
        )
        if not matching_paths:
            errors.append(
                "linked runtime entity missing required owner file: "
                f"{filename}"
            )
            continue
        for relative_path in matching_paths:
            try:
                payload = decode_json_bytes(
                    package.read_bytes(relative_path)
                )
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            actual = payload.get("GameCardId")
            if actual != runtime_card_id:
                errors.append(
                    "linked runtime entity filename/GameCardId mismatch: "
                    f"{filename} owns {runtime_card_id}, got {actual}"
                )
    return errors


def _has_curated_linked_runtime_owner_relation(
    relations: list[dict[str, str]],
) -> bool:
    (
        source_card_id,
        semantic_surface,
        link_kind,
        runtime_card_id,
    ) = AUTHORIZED_HERO_POWER_OWNER
    return any(
        relation
        == {
            "source_card_id": source_card_id,
            "runtime_card_id": runtime_card_id,
            "link_kind": link_kind,
            "semantic_surface": semantic_surface,
            "behavior_block": "BeforeUseHeroPowerBonus",
        }
        for relation in relations
    )


def _has_curated_linked_runtime_owner_file(package_path: Path) -> bool:
    runtime_card_id = AUTHORIZED_HERO_POWER_OWNER[3]
    return any(
        path.is_file()
        for path in (package_path / "CustomConfig").glob(
            f"*/{runtime_card_id}.json"
        )
    )


def _has_curated_linked_runtime_owner_file_view(
    package: PackageView,
) -> bool:
    runtime_card_id = AUTHORIZED_HERO_POWER_OWNER[3]
    return any(
        name.startswith("CustomConfig/")
        and name.endswith(f"/{runtime_card_id}.json")
        and len(name.split("/")) == 3
        for name in package.file_names()
    )


def linked_runtime_owner_projection(
    behavior_plan: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Return the canonical, sorted linked-owner authority projection."""
    projection, _errors = _linked_runtime_relations(behavior_plan)
    return projection


def _linked_runtime_relations(
    behavior_plan: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    relations: list[dict[str, str]] = []
    errors: list[str] = []
    for row in _validated_behavior_plan_rows(behavior_plan):
        source_card_id = str(
            row.get("source_card_id") or row.get("card_id") or ""
        ).strip()
        runtime_card_id = str(
            row.get("runtime_card_id") or row.get("card_id") or ""
        ).strip()
        link_kind = str(row.get("link_kind") or "self").strip()
        if (
            not source_card_id
            or not runtime_card_id
            or (
                source_card_id == runtime_card_id
                and link_kind == "self"
            )
        ):
            continue
        behavior_block = str(row.get("behavior_block") or "").strip()
        semantic_surface = linked_runtime_entity_semantic_surface(
            behavior_block=behavior_block,
            link_kind=link_kind,
        )
        authorization_relation = {
            "source_card_id": source_card_id,
            "semantic_reason": semantic_surface or "",
            "link_kind": link_kind,
            "runtime_card_id": runtime_card_id,
        }
        if (
            row.get("meaningful_runtime_surface") is not True
            or semantic_surface is None
            or not runtime_entity_owner_relation_is_authorized(
                **authorization_relation
            )
        ):
            errors.append(
                f"{LINKED_RUNTIME_ENTITY_RELATION_INVALID}: "
                f"source={source_card_id}, "
                f"semantic={semantic_surface or 'unauthorized'}, "
                f"link={link_kind}, block={behavior_block or 'missing'}, "
                f"runtime={runtime_card_id}"
            )
            continue
        relations.append(
            {
                "source_card_id": source_card_id,
                "runtime_card_id": runtime_card_id,
                "link_kind": link_kind,
                "semantic_surface": semantic_surface,
                "behavior_block": behavior_block,
            }
        )
    return (
        sorted(
            relations,
            key=lambda row: (
                row["source_card_id"],
                row["runtime_card_id"],
                row["link_kind"],
                row["semantic_surface"],
                row["behavior_block"],
            ),
        ),
        errors,
    )


def _validated_behavior_plan_rows(
    behavior_plan: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    rows = behavior_plan.get("rows")
    if not isinstance(rows, list) or any(
        not isinstance(row, Mapping) for row in rows
    ):
        raise ValueError(LINKED_RUNTIME_OWNER_EVIDENCE_INVALID)
    return rows
