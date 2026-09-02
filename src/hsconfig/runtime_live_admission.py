"""Neutral fixed runtime-admission authority, observation, and writer gates."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from hsconfig.package_io import (
    FilesystemPathGuard,
    PathIdentity,
    capture_plain_ancestor_guard,
    path_identity,
    path_identity_from_status,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_no_alternate_data_streams,
    require_plain_directory,
    require_same_identity_resolution,
    secure_unlink_verified,
)


RUNTIME_LIVE_ATTEMPT_ADMISSION_SCHEMA_VERSION = 1
RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES = 64 * 1024
RUNTIME_LIVE_ATTEMPT_ADMISSION_KIND = "live_start_runtime_admission"
RUNTIME_LIVE_ATTEMPT_ADMISSION_NAME = "live-start-active-attempt.json"
RUNTIME_LIVE_ATTEMPT_ADMISSION_FIELDS = frozenset(
    {
        "schema_version",
        "record_kind",
        "run_id",
        "apply_attempt_id",
        "retention_owner_run_id",
        "session_root",
        "session_root_identity",
        "operator_profile_sha256",
        "state_root_identity",
        "runtime_root",
        "runtime_root_identity",
        "output_base_root",
        "output_base_root_identity",
        "output_root",
        "output_root_identity",
        "output_operation_admission_path",
        "output_operation_admission_identity",
        "output_operation_admission_sha256",
        "output_child_binding_sha256",
        "publication_revision",
        "publication_content_root_sha256",
        "package_root_sha256",
        "pre_apply_runtime_snapshot_sha256",
        "apply_invocation_sha256",
        "retention_fence_path",
        "content_sha256",
    }
)


_STANDARD_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_REVISION = re.compile(r"revisions/sha256-[0-9a-f]{64}\Z")
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
    | {
        f"{prefix}{suffix}"
        for prefix in ("com", "lpt")
        for suffix in ("¹", "²", "³")
    }
)
_WINDOWS_INVALID_COMPONENT_CHARACTERS = frozenset('<>"/\\|?*:')
_WINDOWS_UNC_IPC_SHARES = frozenset({"pipe", "mailslot", "ipc$"})


@dataclass(frozen=True, slots=True)
class RuntimeLiveAttemptAdmissionEvidence:
    admission_path: Path
    admission_parent_identity: PathIdentity
    admission_identity: PathIdentity
    admission_sha256: str
    run_id: str
    apply_attempt_id: str
    retention_owner_run_id: str
    session_root: Path
    session_root_identity: PathIdentity
    operator_profile_sha256: str
    state_root_identity: PathIdentity
    runtime_root: Path
    runtime_root_identity: PathIdentity
    output_base_root: Path
    output_base_root_identity: PathIdentity
    output_root: Path
    output_root_identity: PathIdentity
    output_operation_admission_path: Path
    output_operation_admission_identity: PathIdentity
    output_operation_admission_sha256: str
    output_child_binding_sha256: str
    publication_revision: str
    publication_content_root_sha256: str
    package_root_sha256: str
    pre_apply_runtime_snapshot_sha256: str
    apply_invocation_sha256: str
    retention_fence_path: Path


RuntimeLiveAttemptReleaseDisposition = Literal[
    "old_unlinked",
    "already_absent",
    "valid_foreign_successor",
]


@dataclass(frozen=True, slots=True)
class RuntimeLiveAttemptReleaseObservation:
    admission_path: Path
    admission_parent_identity: PathIdentity
    historical_admission_identity: PathIdentity
    historical_admission_sha256: str
    disposition: RuntimeLiveAttemptReleaseDisposition
    foreign_successor_identity: PathIdentity | None
    foreign_successor_sha256: str | None


def runtime_live_attempt_admission_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the one process-independent runtime-admission path."""

    environment = os.environ if environ is None else environ
    raw = environment.get("LOCALAPPDATA")
    if not isinstance(raw, str) or not raw:
        raise ValueError("runtime_live_admission_localappdata_missing")
    root = Path(raw)
    if not root.is_absolute():
        raise ValueError("runtime_live_admission_localappdata_not_absolute")
    _require_windows_safe_absolute_path(
        root,
        error="runtime_live_admission_localappdata_namespace_invalid",
    )
    return root / "HSConfig" / RUNTIME_LIVE_ATTEMPT_ADMISSION_NAME


def build_runtime_live_attempt_admission_bytes(
    *,
    run_id: str,
    apply_attempt_id: str,
    retention_owner_run_id: str,
    session_root: Path,
    session_root_identity: PathIdentity,
    operator_profile_sha256: str,
    state_root_identity: PathIdentity,
    runtime_root: Path,
    runtime_root_identity: PathIdentity,
    output_base_root: Path,
    output_base_root_identity: PathIdentity,
    output_root: Path,
    output_root_identity: PathIdentity,
    output_operation_admission_path: Path,
    output_operation_admission_identity: PathIdentity,
    output_operation_admission_sha256: str,
    output_child_binding_sha256: str,
    publication_revision: str,
    publication_content_root_sha256: str,
    package_root_sha256: str,
    pre_apply_runtime_snapshot_sha256: str,
    apply_invocation_sha256: str,
    retention_fence_path: Path,
) -> bytes:
    """Build the exact immutable canonical runtime-admission document."""

    identifiers = {
        "run_id": _require_run_id(run_id, "run_id"),
        "apply_attempt_id": _require_run_id(
            apply_attempt_id,
            "apply_attempt_id",
        ),
        "retention_owner_run_id": _require_run_id(
            retention_owner_run_id,
            "retention_owner_run_id",
        ),
    }
    digests = {
        field: _require_digest(value, field)
        for field, value in {
            "operator_profile_sha256": operator_profile_sha256,
            "output_operation_admission_sha256": (
                output_operation_admission_sha256
            ),
            "output_child_binding_sha256": output_child_binding_sha256,
            "publication_content_root_sha256": (
                publication_content_root_sha256
            ),
            "package_root_sha256": package_root_sha256,
            "pre_apply_runtime_snapshot_sha256": (
                pre_apply_runtime_snapshot_sha256
            ),
            "apply_invocation_sha256": apply_invocation_sha256,
        }.items()
    }
    revision = _require_revision(publication_revision)
    if revision.removeprefix("revisions/sha256-") != digests[
        "publication_content_root_sha256"
    ].removeprefix("sha256:"):
        raise ValueError("runtime_live_admission_publication_binding_invalid")

    expected_state_root = runtime_live_attempt_admission_path().parent
    state_identity = _require_identity(state_root_identity, "state_root_identity")
    _require_existing_directory_binding(
        expected_state_root,
        expected_identity=state_identity,
        field="state_root",
    )
    canonical_paths = {
        "session_root": _require_existing_directory_binding(
            session_root,
            expected_identity=_require_identity(
                session_root_identity,
                "session_root_identity",
            ),
            field="session_root",
        ),
        "runtime_root": _require_existing_directory_binding(
            runtime_root,
            expected_identity=_require_identity(
                runtime_root_identity,
                "runtime_root_identity",
            ),
            field="runtime_root",
        ),
        "output_base_root": _require_existing_directory_binding(
            output_base_root,
            expected_identity=_require_identity(
                output_base_root_identity,
                "output_base_root_identity",
            ),
            field="output_base_root",
        ),
        "output_root": _require_existing_directory_binding(
            output_root,
            expected_identity=_require_identity(
                output_root_identity,
                "output_root_identity",
            ),
            field="output_root",
        ),
        "output_operation_admission_path": _require_existing_file_binding(
            output_operation_admission_path,
            expected_identity=_require_identity(
                output_operation_admission_identity,
                "output_operation_admission_identity",
            ),
            field="output_operation_admission_path",
        ),
    }
    if canonical_paths["output_root"].parent != canonical_paths[
        "output_base_root"
    ]:
        raise ValueError("runtime_live_admission_output_root_invalid")
    if canonical_paths["output_operation_admission_path"] != (
        expected_state_root / "output-operation-admission.json"
    ):
        raise ValueError("runtime_live_admission_output_operation_path_invalid")

    retention_path = _canonical_absolute_path(
        str(Path(retention_fence_path)),
        "retention_fence_path",
    )
    expected_retention_path = (
        canonical_paths["runtime_root"]
        / ".hsconfig"
        / "attempt-retention"
        / f"{identifiers['apply_attempt_id']}.json"
    )
    if retention_path != expected_retention_path:
        raise ValueError("runtime_live_admission_retention_fence_path_invalid")

    identities = {
        "session_root_identity": _require_identity(
            session_root_identity,
            "session_root_identity",
        ),
        "state_root_identity": state_identity,
        "runtime_root_identity": _require_identity(
            runtime_root_identity,
            "runtime_root_identity",
        ),
        "output_base_root_identity": _require_identity(
            output_base_root_identity,
            "output_base_root_identity",
        ),
        "output_root_identity": _require_identity(
            output_root_identity,
            "output_root_identity",
        ),
        "output_operation_admission_identity": _require_identity(
            output_operation_admission_identity,
            "output_operation_admission_identity",
        ),
    }
    unsigned: dict[str, Any] = {
        "schema_version": RUNTIME_LIVE_ATTEMPT_ADMISSION_SCHEMA_VERSION,
        "record_kind": RUNTIME_LIVE_ATTEMPT_ADMISSION_KIND,
        **identifiers,
        **{name: str(path) for name, path in canonical_paths.items()},
        **{name: list(identity) for name, identity in identities.items()},
        **digests,
        "publication_revision": revision,
        "retention_fence_path": str(retention_path),
    }
    document = {**unsigned, "content_sha256": _self_digest(unsigned)}
    raw = _canonical_json(document)
    if (
        set(document) != RUNTIME_LIVE_ATTEMPT_ADMISSION_FIELDS
        or len(raw) > RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES
    ):
        raise ValueError("runtime_live_admission_document_invalid")
    return raw


def load_runtime_live_attempt_admission() -> (
    RuntimeLiveAttemptAdmissionEvidence | None
):
    """Boundedly observe the fixed final record without creating its parent."""

    admission_path = runtime_live_attempt_admission_path()
    parent = admission_path.parent
    ancestor_guard = _capture_admission_ancestor_guard(admission_path)
    if not path_lexists(parent):
        if path_lexists(admission_path):
            raise ValueError("runtime_live_admission_parent_ambiguous")
        _require_admission_ancestor_guard(ancestor_guard)
        return None
    parent_identity = _require_parent_identity(parent)
    if not path_lexists(admission_path):
        _require_admission_ancestor_guard(ancestor_guard)
        _require_unchanged_parent(parent, parent_identity)
        return None
    try:
        status = plain_file_status(admission_path)
        admission_identity = path_identity_from_status(status)
        require_no_alternate_data_streams(
            admission_path,
            expected_identity=admission_identity,
            expected_parent_identity=parent_identity,
            directory=False,
            expected_size=status.st_size,
        )
        raw = read_file_no_follow(
            admission_path,
            expected_status=status,
            maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        )
        document = _load_canonical_document(raw)
        evidence = _parse_admission_document(
            document,
            raw=raw,
            admission_path=admission_path,
            admission_parent_identity=parent_identity,
            admission_identity=admission_identity,
        )
        if path_identity(admission_path) != admission_identity:
            raise ValueError("runtime_live_admission_identity_changed")
        _require_admission_ancestor_guard(ancestor_guard)
        _require_unchanged_parent(parent, parent_identity)
        return evidence
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith(
            "runtime_live_admission"
        ):
            raise
        raise ValueError("runtime_live_admission_observation_invalid") from error


def require_live_admission_allows_publication(
    *,
    output_root: Path,
    output_root_identity: PathIdentity | None,
) -> None:
    root = _require_caller_path(output_root, "output_root")
    identity = (
        None
        if output_root_identity is None
        else _require_identity(output_root_identity, "output_root_identity")
    )
    observed = load_runtime_live_attempt_admission()
    if observed is None:
        return
    same_path = observed.output_root == root
    same_identity = (
        identity is not None and observed.output_root_identity == identity
    )
    if same_path and identity is not None and not same_identity:
        raise ValueError("runtime_live_admission_output_root_identity_changed")
    if same_path or same_identity:
        raise ValueError("runtime_live_admission_blocks_publication")


def require_live_admission_allows_profile_mutation() -> None:
    if load_runtime_live_attempt_admission() is not None:
        raise ValueError("runtime_live_admission_blocks_profile_mutation")


def require_live_admission_allows_runtime_mutation(
    *,
    runtime_root: Path,
    runtime_root_identity: PathIdentity,
) -> None:
    root = _require_caller_path(runtime_root, "runtime_root")
    identity = _require_identity(runtime_root_identity, "runtime_root_identity")
    observed = load_runtime_live_attempt_admission()
    if observed is None or observed.runtime_root != root:
        return
    if observed.runtime_root_identity != identity:
        raise ValueError("runtime_live_admission_runtime_root_identity_changed")
    raise ValueError("runtime_live_admission_blocks_runtime_mutation")


def require_live_admission_allows_legacy_root_bootstrap(
    *,
    runtime_root: Path,
) -> None:
    root = _require_caller_path(runtime_root, "runtime_root")
    observed = load_runtime_live_attempt_admission()
    if observed is not None and observed.runtime_root == root:
        raise ValueError("runtime_live_admission_blocks_legacy_root_bootstrap")


def release_runtime_live_attempt_exact(
    *,
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeLiveAttemptReleaseObservation:
    """Release only the exact historical record or preserve a valid successor."""

    _require_expected_evidence(expected)
    current = load_runtime_live_attempt_admission()
    observation_arguments = {
        "admission_path": expected.admission_path,
        "admission_parent_identity": expected.admission_parent_identity,
        "historical_admission_identity": expected.admission_identity,
        "historical_admission_sha256": expected.admission_sha256,
    }
    if current is None:
        try:
            current_parent_identity = path_identity(expected.admission_path.parent)
        except OSError as error:
            raise ValueError(
                "runtime_live_admission_release_parent_changed"
            ) from error
        if current_parent_identity != expected.admission_parent_identity:
            raise ValueError("runtime_live_admission_release_parent_changed")
        return RuntimeLiveAttemptReleaseObservation(
            **observation_arguments,
            disposition="already_absent",
            foreign_successor_identity=None,
            foreign_successor_sha256=None,
        )
    if current.admission_parent_identity != expected.admission_parent_identity:
        raise ValueError("runtime_live_admission_release_parent_changed")
    if current.admission_identity == expected.admission_identity:
        if current != expected:
            raise ValueError("runtime_live_admission_release_old_changed")
        try:
            status = plain_file_status(current.admission_path)
            secure_unlink_verified(
                current.admission_path,
                expected_identity=current.admission_identity,
                expected_parent_identity=current.admission_parent_identity,
                expected_size=status.st_size,
                expected_sha256=current.admission_sha256.removeprefix("sha256:"),
            )
        except (OSError, ValueError) as error:
            raise ValueError("runtime_live_admission_release_old_changed") from error
        return RuntimeLiveAttemptReleaseObservation(
            **observation_arguments,
            disposition="old_unlinked",
            foreign_successor_identity=None,
            foreign_successor_sha256=None,
        )
    if (
        current.admission_sha256 == expected.admission_sha256
        or (
            current.run_id == expected.run_id
            and current.apply_attempt_id == expected.apply_attempt_id
        )
    ):
        raise ValueError("runtime_live_admission_release_replaced_ambiguous")
    return RuntimeLiveAttemptReleaseObservation(
        **observation_arguments,
        disposition="valid_foreign_successor",
        foreign_successor_identity=current.admission_identity,
        foreign_successor_sha256=current.admission_sha256,
    )


def _require_exact_runtime_live_attempt(
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeLiveAttemptAdmissionEvidence:
    _require_expected_evidence(expected)
    observed = load_runtime_live_attempt_admission()
    if observed != expected:
        raise ValueError("runtime_live_admission_exact_binding_invalid")
    return observed


def _load_canonical_document(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES:
        raise ValueError("runtime_live_admission_size_invalid")
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
        raise ValueError("runtime_live_admission_bytes_invalid")

    def reject_constant(value: str) -> None:
        raise ValueError(f"runtime_live_admission_non_finite:{value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("runtime_live_admission_duplicate_key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("runtime_live_admission_json_invalid") from error
    if not isinstance(value, dict):
        raise ValueError("runtime_live_admission_root_invalid")
    try:
        canonical = _canonical_json(value)
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("runtime_live_admission_json_invalid") from error
    if canonical != raw:
        raise ValueError("runtime_live_admission_not_canonical")
    return value


def _parse_admission_document(
    document: dict[str, Any],
    *,
    raw: bytes,
    admission_path: Path,
    admission_parent_identity: PathIdentity,
    admission_identity: PathIdentity,
) -> RuntimeLiveAttemptAdmissionEvidence:
    if set(document) != RUNTIME_LIVE_ATTEMPT_ADMISSION_FIELDS:
        raise ValueError("runtime_live_admission_fields_invalid")
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"]
        != RUNTIME_LIVE_ATTEMPT_ADMISSION_SCHEMA_VERSION
    ):
        raise ValueError("runtime_live_admission_schema_invalid")
    if document["record_kind"] != RUNTIME_LIVE_ATTEMPT_ADMISSION_KIND:
        raise ValueError("runtime_live_admission_kind_invalid")
    _require_self_digest(document)

    run_id = _require_run_id(document["run_id"], "run_id")
    apply_attempt_id = _require_run_id(
        document["apply_attempt_id"],
        "apply_attempt_id",
    )
    retention_owner_run_id = _require_run_id(
        document["retention_owner_run_id"],
        "retention_owner_run_id",
    )
    session_root = _canonical_absolute_path(document["session_root"], "session_root")
    runtime_root = _canonical_absolute_path(document["runtime_root"], "runtime_root")
    output_base_root = _canonical_absolute_path(
        document["output_base_root"],
        "output_base_root",
    )
    output_root = _canonical_absolute_path(document["output_root"], "output_root")
    output_operation_path = _canonical_absolute_path(
        document["output_operation_admission_path"],
        "output_operation_admission_path",
    )
    retention_fence_path = _canonical_absolute_path(
        document["retention_fence_path"],
        "retention_fence_path",
    )
    if output_root.parent != output_base_root:
        raise ValueError("runtime_live_admission_output_root_invalid")
    if output_operation_path != admission_path.parent / "output-operation-admission.json":
        raise ValueError("runtime_live_admission_output_operation_path_invalid")
    if retention_fence_path != (
        runtime_root
        / ".hsconfig"
        / "attempt-retention"
        / f"{apply_attempt_id}.json"
    ):
        raise ValueError("runtime_live_admission_retention_fence_path_invalid")

    state_root_identity = _require_identity(
        document["state_root_identity"],
        "state_root_identity",
    )
    if state_root_identity != admission_parent_identity:
        raise ValueError("runtime_live_admission_state_root_identity_changed")
    revision = _require_revision(document["publication_revision"])
    publication_digest = _require_digest(
        document["publication_content_root_sha256"],
        "publication_content_root_sha256",
    )
    if revision.removeprefix("revisions/sha256-") != publication_digest.removeprefix(
        "sha256:"
    ):
        raise ValueError("runtime_live_admission_publication_binding_invalid")
    digests = {
        field: _require_digest(document[field], field)
        for field in (
            "operator_profile_sha256",
            "output_operation_admission_sha256",
            "output_child_binding_sha256",
            "package_root_sha256",
            "pre_apply_runtime_snapshot_sha256",
            "apply_invocation_sha256",
        )
    }
    return RuntimeLiveAttemptAdmissionEvidence(
        admission_path=admission_path,
        admission_parent_identity=admission_parent_identity,
        admission_identity=admission_identity,
        admission_sha256="sha256:" + sha256(raw).hexdigest(),
        run_id=run_id,
        apply_attempt_id=apply_attempt_id,
        retention_owner_run_id=retention_owner_run_id,
        session_root=session_root,
        session_root_identity=_require_identity(
            document["session_root_identity"],
            "session_root_identity",
        ),
        operator_profile_sha256=digests["operator_profile_sha256"],
        state_root_identity=state_root_identity,
        runtime_root=runtime_root,
        runtime_root_identity=_require_identity(
            document["runtime_root_identity"],
            "runtime_root_identity",
        ),
        output_base_root=output_base_root,
        output_base_root_identity=_require_identity(
            document["output_base_root_identity"],
            "output_base_root_identity",
        ),
        output_root=output_root,
        output_root_identity=_require_identity(
            document["output_root_identity"],
            "output_root_identity",
        ),
        output_operation_admission_path=output_operation_path,
        output_operation_admission_identity=_require_identity(
            document["output_operation_admission_identity"],
            "output_operation_admission_identity",
        ),
        output_operation_admission_sha256=digests[
            "output_operation_admission_sha256"
        ],
        output_child_binding_sha256=digests["output_child_binding_sha256"],
        publication_revision=revision,
        publication_content_root_sha256=publication_digest,
        package_root_sha256=digests["package_root_sha256"],
        pre_apply_runtime_snapshot_sha256=digests[
            "pre_apply_runtime_snapshot_sha256"
        ],
        apply_invocation_sha256=digests["apply_invocation_sha256"],
        retention_fence_path=retention_fence_path,
    )


def _require_expected_evidence(expected: object) -> None:
    if not isinstance(expected, RuntimeLiveAttemptAdmissionEvidence):
        raise TypeError("runtime_live_admission_evidence_required")
    if expected.admission_path != runtime_live_attempt_admission_path():
        raise ValueError("runtime_live_admission_expected_path_invalid")
    _require_identity(
        expected.admission_parent_identity,
        "admission_parent_identity",
    )
    _require_identity(expected.admission_identity, "admission_identity")
    _require_digest(expected.admission_sha256, "admission_sha256")


def _require_parent_identity(parent: Path) -> PathIdentity:
    try:
        require_plain_directory(parent)
        require_same_identity_resolution(parent)
        identity = path_identity(parent)
        _require_unchanged_parent(parent, identity)
        return identity
    except (OSError, ValueError) as error:
        raise ValueError("runtime_live_admission_parent_invalid") from error


def _capture_admission_ancestor_guard(path: Path) -> FilesystemPathGuard:
    try:
        guard = capture_plain_ancestor_guard(path)
        guard.validate()
        return guard
    except (OSError, ValueError) as error:
        raise ValueError("runtime_live_admission_parent_invalid") from error


def _require_admission_ancestor_guard(guard: FilesystemPathGuard) -> None:
    try:
        guard.validate()
    except (OSError, ValueError) as error:
        raise ValueError("runtime_live_admission_parent_identity_changed") from error


def _require_unchanged_parent(
    parent: Path,
    expected_identity: PathIdentity,
) -> None:
    try:
        require_plain_directory(parent)
        require_same_identity_resolution(parent)
        if path_identity(parent) != expected_identity:
            raise ValueError("runtime_live_admission_parent_identity_changed")
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith(
            "runtime_live_admission"
        ):
            raise
        raise ValueError("runtime_live_admission_parent_identity_changed") from error


def _require_existing_directory_binding(
    path: Path,
    *,
    expected_identity: PathIdentity,
    field: str,
) -> Path:
    candidate = _canonical_absolute_path(str(Path(path)), field)
    try:
        require_plain_directory(candidate)
        require_same_identity_resolution(candidate)
        if path_identity(candidate) != expected_identity:
            raise ValueError(f"runtime_live_admission_{field}_identity_changed")
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith(
            "runtime_live_admission"
        ):
            raise
        raise ValueError(f"runtime_live_admission_{field}_invalid") from error
    return candidate


def _require_existing_file_binding(
    path: Path,
    *,
    expected_identity: PathIdentity,
    field: str,
) -> Path:
    candidate = _canonical_absolute_path(str(Path(path)), field)
    try:
        status = plain_file_status(candidate)
        if path_identity_from_status(status) != expected_identity:
            raise ValueError(f"runtime_live_admission_{field}_identity_changed")
        require_same_identity_resolution(candidate, expected_status=status)
    except (OSError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith(
            "runtime_live_admission"
        ):
            raise
        raise ValueError(f"runtime_live_admission_{field}_invalid") from error
    return candidate


def _require_caller_path(value: Path, field: str) -> Path:
    return _canonical_absolute_path(str(Path(value)), field)


def _require_identity(value: object, field: str) -> PathIdentity:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(type(item) is not int for item in value)
        or any(item < 0 for item in value)
    ):
        raise ValueError(f"runtime_live_admission_{field}_invalid")
    return value[0], value[1], value[2]


def _require_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _STANDARD_SHA256.fullmatch(value) is None:
        raise ValueError(f"runtime_live_admission_{field}_invalid")
    return value


def _require_run_id(value: object, field: str) -> str:
    if not isinstance(value, str) or _RUN_ID.fullmatch(value) is None:
        raise ValueError(f"runtime_live_admission_{field}_invalid")
    return value


def _require_revision(value: object) -> str:
    if not isinstance(value, str) or _REVISION.fullmatch(value) is None:
        raise ValueError("runtime_live_admission_publication_revision_invalid")
    return value


def _canonical_absolute_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"runtime_live_admission_{field}_invalid")
    path = Path(value)
    if (
        not path.is_absolute()
        or os.path.normpath(value) != value
        or str(path) != value
    ):
        raise ValueError(f"runtime_live_admission_{field}_invalid")
    return _require_windows_safe_absolute_path(
        path,
        error=f"runtime_live_admission_{field}_namespace_invalid",
    )


def _require_windows_safe_absolute_path(path: Path, *, error: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError(error)
    if os.name != "nt":
        return candidate
    text = str(candidate)
    lowered = text.casefold()
    if lowered.startswith(("\\\\?\\", "\\\\.\\", "\\??\\")):
        raise ValueError(error)
    drive = candidate.drive
    if drive.startswith("\\\\"):
        authority_components = drive[2:].split("\\")
        if len(authority_components) != 2:
            raise ValueError(error)
        server, share = authority_components
        _require_windows_safe_component(
            server,
            error=error,
            reject_device_name=False,
        )
        _require_windows_safe_component(
            share,
            error=error,
            reject_device_name=False,
        )
        if share.casefold() in _WINDOWS_UNC_IPC_SHARES:
            raise ValueError(error)
    elif re.fullmatch(r"[A-Za-z]:", drive):
        pass
    else:
        raise ValueError(error)
    for component in candidate.parts[1:]:
        _require_windows_safe_component(
            component,
            error=error,
            reject_device_name=True,
        )
    return candidate


def _require_windows_safe_component(
    component: str,
    *,
    error: str,
    reject_device_name: bool,
) -> None:
    if (
        not component
        or component in {".", ".."}
        or component.endswith((".", " "))
        or any(ord(character) < 32 for character in component)
        or any(
            character in _WINDOWS_INVALID_COMPONENT_CHARACTERS
            for character in component
        )
    ):
        raise ValueError(error)
    if reject_device_name:
        device_stem = component.split(".", 1)[0].rstrip(" .").casefold()
        if device_stem in _WINDOWS_RESERVED_NAMES:
            raise ValueError(error)


def _require_self_digest(document: dict[str, Any]) -> None:
    content_sha256 = _require_digest(document["content_sha256"], "content_sha256")
    unsigned = dict(document)
    del unsigned["content_sha256"]
    if content_sha256 != _self_digest(unsigned):
        raise ValueError("runtime_live_admission_content_sha256_invalid")


def _self_digest(unsigned: object) -> str:
    return "sha256:" + sha256(_canonical_json(unsigned)).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = (
    "RUNTIME_LIVE_ATTEMPT_ADMISSION_FIELDS",
    "RUNTIME_LIVE_ATTEMPT_ADMISSION_KIND",
    "RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES",
    "RUNTIME_LIVE_ATTEMPT_ADMISSION_NAME",
    "RUNTIME_LIVE_ATTEMPT_ADMISSION_SCHEMA_VERSION",
    "RuntimeLiveAttemptAdmissionEvidence",
    "RuntimeLiveAttemptReleaseDisposition",
    "RuntimeLiveAttemptReleaseObservation",
    "build_runtime_live_attempt_admission_bytes",
    "load_runtime_live_attempt_admission",
    "release_runtime_live_attempt_exact",
    "require_live_admission_allows_legacy_root_bootstrap",
    "require_live_admission_allows_profile_mutation",
    "require_live_admission_allows_publication",
    "require_live_admission_allows_runtime_mutation",
    "runtime_live_attempt_admission_path",
)
