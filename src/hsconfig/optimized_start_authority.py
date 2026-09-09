"""Manifest-dispatched optimized-start authority loading."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, TypeAlias

from hsconfig.configuration_mode import (
    OptimizedStartAuthoritySchema,
    optimized_start_authority_schema_from_manifest,
)
from hsconfig.input_snapshot_manifest import (
    INPUT_SNAPSHOT_FIELDS,
    INPUT_SNAPSHOT_MAX_BYTES,
    INPUT_SNAPSHOT_SCHEMA_VERSION,
    ValidatedInputSnapshotManifest,
    validate_input_snapshot_manifest_document,
)
from hsconfig.package_io import (
    PathIdentity,
    path_identity,
    plain_file_status,
    require_plain_directory,
)
from hsconfig.starter_candidate import (
    ValidatedStarterCandidate,
    validate_starter_candidate,
)
from hsconfig.starter_context import (
    StarterContext,
    validate_starter_context_document,
)
from hsconfig.starter_contract import (
    QUALITY_STARTER_CONTEXT_FIELDS,
    QUALITY_STARTER_CANDIDATE_FIELDS,
    QUALITY_STARTER_REVIEW_FIELDS,
    QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
    live_contract_for_versions,
    SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
    SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
    STARTER_CANDIDATE_MAX_BYTES,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_DECISION_FILENAME,
    STARTER_REVIEW_FIELDS,
    STARTER_REVIEW_MAX_BYTES,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_decision import (
    ValidatedStarterSelection,
    load_validated_starter_selection,
)
from hsconfig.starter_document import load_starter_document
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_review import (
    ValidatedStarterReview,
    validate_starter_review,
)
from hsconfig.visionai_registry import (
    optimized_start_report_paths_for_manifest,
)


@dataclass(frozen=True, slots=True)
class ValidatedSingleStarterApproval:
    snapshot: ValidatedInputSnapshotManifest
    context: StarterContext
    candidate: ValidatedStarterCandidate
    review: ValidatedStarterReview
    validation_receipt: FrozenJsonDocument | None = None


@dataclass(frozen=True, slots=True)
class _ReportSetBinding:
    root_identity: PathIdentity
    file_states: tuple[
        tuple[str, tuple[int, int, int, int, int, int | None]],
        ...,
    ]


ValidatedOptimizedStartAuthority: TypeAlias = (
    ValidatedStarterSelection | ValidatedSingleStarterApproval
)


def load_optimized_start_authority(
    *,
    report_root: Path,
    manifest: Mapping[str, Any],
) -> ValidatedOptimizedStartAuthority:
    """Load exactly the authority schema selected by the package manifest."""

    schema = optimized_start_authority_schema_from_manifest(manifest)
    expected_paths = optimized_start_report_paths_for_manifest(manifest)
    if schema is None or not expected_paths:
        raise ValueError("optimized_start_authority_not_enabled")

    root = Path(report_root)
    report_set_binding = _require_exact_report_set(root, expected_paths)
    if schema == "legacy_five_doc":
        authority = _load_legacy_authority(root)
    elif schema in {"single_candidate_review_v1", "single_candidate_review_v2"}:
        authority = _load_single_candidate_approval(
            root, quality=schema == "single_candidate_review_v2"
        )
    else:
        raise ValueError("optimized_start_authority_schema_invalid")
    _require_exact_report_set(
        root,
        expected_paths,
        expected_binding=report_set_binding,
    )
    return authority


def _require_exact_report_set(
    root: Path,
    expected_paths: tuple[str, ...],
    *,
    expected_binding: _ReportSetBinding | None = None,
) -> _ReportSetBinding:
    expected_names = tuple(Path(path).name for path in expected_paths)
    if len(set(expected_names)) != len(expected_names):
        raise ValueError("optimized_start_authority_report_set_invalid")
    try:
        require_plain_directory(root)
        current_root_identity = path_identity(root)
        if expected_binding is not None and (
            current_root_identity != expected_binding.root_identity
        ):
            raise ValueError("optimized_start_authority_report_set_invalid")
        names: list[str] = []
        file_states: list[
            tuple[str, tuple[int, int, int, int, int, int | None]]
        ] = []
        with os.scandir(root) as entries:
            for entry in entries:
                if len(names) >= len(expected_names):
                    raise ValueError(
                        "optimized_start_authority_report_set_invalid"
                    )
                status = plain_file_status(Path(entry.path))
                names.append(entry.name)
                file_states.append((entry.name, _report_file_state(status)))
        require_plain_directory(root)
        if path_identity(root) != current_root_identity:
            raise ValueError("optimized_start_authority_report_set_invalid")
    except (OSError, ValueError) as error:
        if str(error) == "optimized_start_authority_report_set_invalid":
            raise
        raise ValueError(
            "optimized_start_authority_report_set_invalid"
        ) from error
    if len(names) != len(expected_names) or set(names) != set(expected_names):
        raise ValueError("optimized_start_authority_report_set_invalid")
    binding = _ReportSetBinding(
        root_identity=current_root_identity,
        file_states=tuple(sorted(file_states)),
    )
    if expected_binding is not None and binding != expected_binding:
        raise ValueError("optimized_start_authority_report_set_invalid")
    return binding


def _report_file_state(
    status: os.stat_result,
) -> tuple[int, int, int, int, int, int | None]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        None if os.name == "nt" else status.st_ctime_ns,
    )


def _load_legacy_authority(root: Path) -> ValidatedStarterSelection:
    context = validate_starter_context_document(
        load_starter_document(
            root / "starter_context.json",
            maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
            expected_fields=STARTER_CONTEXT_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
    )
    return load_validated_starter_selection(
        root / STARTER_DECISION_FILENAME,
        current_context=context,
    )


def _load_single_candidate_approval(
    root: Path,
    *,
    quality: bool = False,
) -> ValidatedSingleStarterApproval:
    version = 3 if quality else 2
    snapshot_document = load_starter_document(
        root / "input_snapshot_manifest.json",
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
        load_starter_document(
            root / "starter_context.json",
            maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
            expected_fields=QUALITY_STARTER_CONTEXT_FIELDS
            if quality
            else SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
            schema_version=version,
        )
    )
    candidate = validate_starter_candidate(
        load_starter_document(
            root / "starter_config_candidate.json",
            maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
            expected_fields=QUALITY_STARTER_CANDIDATE_FIELDS
            if quality
            else SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
            schema_version=version,
        ),
        context=context,
    )
    receipt = (
        load_starter_document(
            root / "candidate_validation_receipt.json",
            maximum_bytes=512 * 1024,
            expected_fields=QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
            schema_version=2,
        ).document
        if quality
        else None
    )
    review = validate_starter_review(
        load_starter_document(
            root / "starter_config_review.json",
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

    context_value = context.document.to_value()
    candidate_value = candidate.document.to_value()
    review_value = review.document.to_value()
    valid = (
        context_value["input_snapshot_manifest_sha256"]
        == snapshot.document.content_sha256
        and candidate_value["starter_context_sha256"]
        == context.document.content_sha256
        and review.starter_context_sha256
        == context.document.content_sha256
        and candidate.candidate_id == "lead"
        and review.candidate_id == candidate.candidate_id
        and review.candidate_revision == candidate.candidate_revision
        and review.candidate_sha256 == candidate.document.content_sha256
        and review.review_status == "approved"
        and review.revision_requests == ()
        and review.confidence in {"high", "limited"}
        and review_value["candidate_sha256"]
        == candidate.document.content_sha256
    )
    if not valid:
        raise ValueError("single_starter_approval_invalid")
    return ValidatedSingleStarterApproval(
        snapshot=snapshot,
        context=context,
        candidate=candidate,
        review=review,
        validation_receipt=receipt,
    )


__all__ = (
    "OptimizedStartAuthoritySchema",
    "ValidatedOptimizedStartAuthority",
    "ValidatedSingleStarterApproval",
    "load_optimized_start_authority",
)
