"""Frozen-authority live-start prepublication and guarded publication seams."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date
import time
import json
import os
import re
import secrets
import stat
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from hearthstone.deckstrings import parse_deckstring

from hsconfig import live_start_session as _session
from hsconfig import output_publisher as _publisher
from hsconfig import published_apply as _published_apply
from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.atomic_io import (
    AtomicWriteConflictError,
    ExclusiveFileLock,
    atomic_commit_bound_staging_no_replace,
    atomic_materialize_staging_bytes,
    atomic_write_reserved_bytes,
    no_fault,
)
from hsconfig.configure_run_model import (
    ConfigureRunModel,
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.evidence_contract import load_policy_profile
from hsconfig.deck_identity import build_deck_identity
from hsconfig.input_loading import load_cards
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.globalvalues_decisions import (
    normalize_globalvalues_decision_baseline,
)
from hsconfig.hearthstonejson import (
    fetch_card_snapshot,
    fetch_latest_cards,
    fetch_latest_collectible_cards,
)
from hsconfig.input_snapshot_manifest import (
    FrozenCompilerInputs,
    _validate_deck_and_card_closure,
    _load_frozen_compiler_inputs,
    freeze_compiler_inputs,
    load_frozen_compiler_inputs,
)
from hsconfig.live_start_faults import (
    LiveStartFaultHook,
    LiveStartFaultPoint,
    invoke_live_start_fault,
    no_live_start_fault,
)
from hsconfig.live_start_session import (
    LiveStartPhase,
    LiveStartSession,
    LiveStartSessionLease,
    SessionCapabilityError,
    SessionConflictError,
)
from hsconfig.operator_profile import (
    DeckOutputBinding,
    OperatorProfile,
    OperatorProfileLease,
    derive_deck_output_binding,
    load_operator_profile,
    lease_operator_profile,
    revalidate_operator_profile,
    revalidate_operator_profile_lease,
)
from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import load_operator_summary_inputs
from hsconfig.optimized_start_authority import ValidatedSingleStarterApproval
from hsconfig.output_operation_admission import (
    OutputOperationAdmissionEvidence,
    OutputOperationAdmissionLease,
    build_output_operation_admission_bytes,
    lease_output_operation_admission,
    observe_output_operation_admission_under_lease,
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
)
from hsconfig.output_publisher import (
    build_output_child_claim_bytes,
    output_child_claim_path,
    output_child_claim_staging_inner_temp_path,
    output_child_claim_staging_path,
)
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    verify_package_derivation_receipt_from_view,
)
from hsconfig.package_io import (
    PathIdentity,
    PlainDirectoryMutationGuard,
    hold_plain_directory,
    path_identity,
    path_identity_from_status,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_no_alternate_data_streams,
    require_plain_directory,
    secure_create_directory,
    secure_replace,
    secure_rmdir_verified,
    secure_unlink,
    secure_unlink_verified,
    snapshot_bounded_filesystem_package,
    status_is_reparse,
)
from hsconfig.package_request import (
    FrozenJsonDocument,
    FrozenApprovedLiveConfigureRequest,
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
)
from hsconfig.preconfig_context import build_preconfig_context
from hsconfig.runtime_apply import plan_apply_package
from hsconfig.strict_package_validation import (
    strict_validation_passed,
    validate_complete_configure_run_from_view,
)
from hsconfig.starter_candidate import (
    STARTER_CANDIDATE_FINDING_CODES,
    ValidatedStarterCandidate,
    validate_starter_candidate,
)
from hsconfig.starter_context import (
    StarterContext,
    build_quality_starter_context,
    build_single_candidate_starter_context,
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
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_REVIEW_FIELDS,
    STARTER_REVIEW_MAX_BYTES,
)
from hsconfig.starter_document import (
    StarterDocument,
    load_starter_document,
    seal_starter_document,
)
from hsconfig.starter_review import ValidatedStarterReview, validate_starter_review


_PACKAGE_RECEIPT_LOGICAL = "receipts/package_validation.json"
_PREPUBLICATION_RECEIPT_LOGICAL = "receipts/prepublication_apply_check.json"
_MAX_RECEIPT_BYTES = 256 * 1024
_RUNTIME_GRAMMAR_VERSION = "visionai-runtime-v1"
_COMPILER_CONTRACT_ID = "hsconfig-live-start-v1"
_PRE_SESSION_SUMMARY_KIND = "live_start_pre_session_result"


@dataclass(frozen=True, slots=True)
class LiveStartRequest:
    deck_name: str
    deck_code: str
    preview_requested: bool


@dataclass(frozen=True, slots=True)
class LiveStartResult:
    status: _session.LiveStartTerminalStatus
    run_root: Path | None
    summary: FrozenJsonDocument


@dataclass(frozen=True, slots=True)
class LiveStartPreparation:
    run_root: Path
    starter_context_path: Path
    candidate_revision: Literal[1, 2, 3]
    visible_limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidatedPrepublication:
    rendered: RenderedConfigureRun
    work_root: Path
    work_root_identity: PathIdentity
    package_root: Path
    package_validation_receipt: FrozenJsonDocument
    diagnostic_receipt: FrozenJsonDocument
    updated_session: LiveStartSession


def _emit_pipeline_event(
    _event: str,
    _payload: Mapping[str, str] | None = None,
) -> None:
    """Internal observation seam used only by tests and composition code."""


def build_frozen_live_configure_run(
    *, request: ResolvedPackageRequest | FrozenApprovedLiveConfigureRequest
) -> ConfigureRunModel:
    """Compile one run solely from the request's sealed frozen authority."""

    if not isinstance(request, (ResolvedPackageRequest, FrozenApprovedLiveConfigureRequest)):
        raise TypeError("resolved_package_request_required")
    frozen = request.frozen_compiler_inputs
    approval = request.starter_approval
    if frozen is None or approval is None:
        raise ValueError("frozen_single_starter_authority_required")
    package = assemble_package(compile_package(request))
    return create_configure_run_model(
        package=package,
        stage_artifacts={
            "01_manifest/input_snapshot_manifest.json": (
                frozen.manifest.document.canonical_json
            ),
            "02_source_documents/source_documents.json": (
                frozen.source_documents.canonical_json
            ),
            "03_research/starter_context.json": (
                approval.context.document.canonical_json
            ),
        },
    )


@contextmanager
def lease_validated_prepublication(
    *,
    run_model: ConfigureRunModel,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_root: Path,
) -> Iterator[ValidatedPrepublication]:
    """Public write-free prepublication wrapper with no fault selector."""

    with _lease_validated_prepublication(
        run_model=run_model,
        session_lease=session_lease,
        expected_session=expected_session,
        runtime_root=runtime_root,
        fault_hook=no_live_start_fault,
    ) as validated:
        yield validated


@contextmanager
def _lease_validated_prepublication(
    *,
    run_model: ConfigureRunModel,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_root: Path,
    fault_hook: LiveStartFaultHook,
) -> Iterator[ValidatedPrepublication]:
    """Materialize, validate, and fake-plan one exact direct package."""

    _require_prepublication_capabilities(
        run_model=run_model,
        session_lease=session_lease,
        expected_session=expected_session,
        runtime_root=runtime_root,
    )
    compiler_inputs, operator_bindings = _frozen_stage_bindings(run_model)
    current = _session.validate_resume_under_lock(
        session_lease=session_lease,
        expected_deck_code_sha256=str(
            compiler_inputs["deck_code_sha256"]
        ),
        expected_input_snapshot_manifest_sha256=(
            expected_session.input_snapshot_manifest_sha256
        ),
        expected_runtime_grammar_version=str(
            compiler_inputs["runtime_grammar_version"]
        ),
        expected_compiler_contract_id=str(
            compiler_inputs["compiler_contract_id"]
        ),
    )
    if current.content_sha256 != expected_session.content_sha256:
        raise SessionConflictError("live_start_session_predecessor_changed")
    prepublication_was_already_committed = (
        current.phase is LiveStartPhase.PREPUBLICATION_CHECK_PASSED
    )
    if current.phase not in {
        LiveStartPhase.REVIEW_APPROVED,
        LiveStartPhase.PACKAGE_VALIDATED,
        LiveStartPhase.PREPUBLICATION_CHECK_PASSED,
    }:
        raise SessionConflictError("live_start_prepublication_phase_invalid")
    if Path(runtime_root).resolve(strict=True) != Path(
        str(operator_bindings["runtime_root"])
    ):
        raise ValueError("live_start_runtime_root_precondition_changed")
    if path_identity(Path(runtime_root)) != tuple(
        operator_bindings["runtime_root_identity"]
    ):
        raise ValueError("live_start_runtime_root_identity_changed")

    quality_frozen = None
    if current.schema_version == 2:
        quality_frozen = _load_frozen_compiler_inputs(
            session_lease.session_root, rebind_operator=False,
        )
        if (
            quality_frozen.manifest.document.content_sha256
            != current.input_snapshot_manifest_sha256
        ):
            raise SessionConflictError("live_start_input_snapshot_mismatch")

    rendered = render_configure_run_model(run_model)
    _emit_pipeline_event("rendered")
    current, work_root, work_identity, work_binding = _materialize_work_run(
        rendered=rendered,
        session_lease=session_lease,
        current=current,
        fault_hook=fault_hook,
    )
    package_root = work_root / "04_package"
    package_receipt = _validate_and_install_package_receipt(
        rendered=rendered,
        work_root=work_root,
        work_binding=work_binding,
        package_root=package_root,
        session_lease=session_lease,
        current=current,
        fault_hook=fault_hook,
        frozen_compiler_inputs=quality_frozen,
    )
    current = package_receipt[0]
    package_document = package_receipt[1]
    diagnostic = _plan_and_install_prepublication_receipt(
        package_root=package_root,
        package_root_sha256=str(
            package_document.to_value()["package_root_sha256"]
        ),
        runtime_root=Path(runtime_root),
        bound_date=str(compiler_inputs["bound_date"]),
        session_lease=session_lease,
        current=current,
        fault_hook=fault_hook,
        frozen_compiler_inputs=quality_frozen,
    )
    current, diagnostic_document = diagnostic
    if (
        current.phase is LiveStartPhase.PREPUBLICATION_CHECK_PASSED
        and not prepublication_was_already_committed
    ):
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_PREPUBLICATION_CAS,
        )
    validated = ValidatedPrepublication(
        rendered=rendered,
        work_root=work_root,
        work_root_identity=work_identity,
        package_root=package_root,
        package_validation_receipt=package_document,
        diagnostic_receipt=diagnostic_document,
        updated_session=current,
    )
    yield validated


def _require_prepublication_capabilities(
    *,
    run_model: ConfigureRunModel,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_root: Path,
) -> None:
    if (
        not isinstance(run_model, ConfigureRunModel)
        or not isinstance(session_lease, LiveStartSessionLease)
        or not isinstance(expected_session, LiveStartSession)
        or not isinstance(runtime_root, Path)
    ):
        raise SessionCapabilityError(
            "live_start_prepublication_capability_invalid"
        )


def _frozen_stage_bindings(
    run_model: ConfigureRunModel,
) -> tuple[dict[str, Any], dict[str, Any]]:
    artifact = next(
        item
        for item in run_model.stage_artifacts
        if item.relative_path
        == "01_manifest/input_snapshot_manifest.json"
    )
    value = json.loads(artifact.content)
    if not isinstance(value, dict):
        raise ValueError("live_start_frozen_manifest_invalid")
    compiler = value.get("compiler_inputs")
    operator = value.get("operator_bindings")
    if not isinstance(compiler, dict) or not isinstance(operator, dict):
        raise ValueError("live_start_frozen_manifest_invalid")
    return compiler, operator


def _materialize_work_run(
    *,
    rendered: RenderedConfigureRun,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    fault_hook: LiveStartFaultHook,
) -> tuple[LiveStartSession, Path, PathIdentity, dict[str, Any]]:
    state_root = session_lease.session_root.parent.parent
    work_parent = state_root / "work"
    work_root = work_parent / f"live-start-{current.run_id}"
    rendered_digest = "sha256:" + rendered.content_root_sha256
    actions = _prepublication_materialization_actions(rendered)
    pending = current.pending_transition
    binding = current.prepublication_work_binding
    with hold_plain_directory(state_root) as state_guard:
        if not path_lexists(work_parent):
            if binding is not None or pending is not None:
                raise ValueError(
                    "live_start_prepublication_work_parent_identity_changed"
                )
            work_parent_identity = state_guard.create_directory("work")
        else:
            require_plain_directory(work_parent)
            work_parent_identity = path_identity(work_parent)
        with state_guard.hold_child_directory(
            "work",
            expected_identity=work_parent_identity,
        ) as work_parent_guard:
            if isinstance(binding, Mapping):
                if (
                    Path(str(binding["work_parent_path"])) != work_parent
                    or tuple(binding["work_parent_identity"])
                    != work_parent_identity
                    or Path(str(binding["work_root"])) != work_root
                ):
                    raise ValueError(
                        "live_start_prepublication_work_binding_changed"
                    )
                work_identity = tuple(binding["work_root_identity"])
                with _hold_bound_materialized_work_root(
                    work_parent_guard=work_parent_guard,
                    work_root=work_root,
                    expected_identity=work_identity,
                ):
                    work_binding = _rebuild_prepublication_work_binding(
                        rendered=rendered,
                        work_parent=work_parent,
                        work_parent_identity=work_parent_identity,
                        work_root=work_root,
                        work_identity=work_identity,
                    )
                if dict(binding) != work_binding:
                    raise ValueError(
                        "live_start_prepublication_work_binding_changed"
                    )
                return current, work_root, work_identity, work_binding

            if pending is None:
                prepared = _session._empty_pending_transition(
                    session=current,
                    operation="materialize_prepublication_work",
                    external_file_action=None,
                )
                prepared.update(
                    {
                        "rendered_model_sha256": rendered_digest,
                        "work_parent_path": str(work_parent),
                        "work_parent_identity": work_parent_identity,
                        "work_root": str(work_root),
                        "actions": actions,
                    }
                )
                current = _session._transition_receipt_authorized_under_lock(
                    session_lease=session_lease,
                    expected_session=current,
                    event="same_phase_cas",
                    changes={
                        "pending_transition": _session._seal_pending(prepared)
                    },
                )
                invoke_live_start_fault(
                    fault_hook,
                    LiveStartFaultPoint.AFTER_PENDING_TRANSITION_CAS,
                )
                pending = current.pending_transition
            if (
                not isinstance(pending, Mapping)
                or pending.get("operation")
                != "materialize_prepublication_work"
                or pending.get("rendered_model_sha256") != rendered_digest
                or pending.get("work_parent_path") != str(work_parent)
                or tuple(pending.get("work_parent_identity", ()))
                != work_parent_identity
                or pending.get("work_root") != str(work_root)
                or list(pending.get("actions", ())) != actions
            ):
                raise SessionConflictError(
                    "live_start_prepublication_cursor_invalid"
                )
            if pending.get("stage") == "PREPARED":
                if path_lexists(work_root):
                    status = work_parent_guard.child_status(work_root.name)
                    work_identity = path_identity_from_status(status)
                    if (
                        not stat.S_ISDIR(status.st_mode)
                        or status_is_reparse(status)
                    ):
                        raise ValueError(
                            "live_start_prepublication_work_residue_present"
                        )
                    with work_parent_guard.hold_child_directory(
                        work_root.name,
                        expected_identity=work_identity,
                    ) as unbound_root_guard:
                        if any(unbound_root_guard.path.iterdir()):
                            raise ValueError(
                                "live_start_prepublication_work_residue_present"
                            )
                        require_no_alternate_data_streams(
                            unbound_root_guard.path,
                            expected_identity=work_identity,
                            expected_parent_identity=work_parent_identity,
                            directory=True,
                            expected_size=None,
                        )
                        unbound_root_guard.validate()
                else:
                    work_identity = work_parent_guard.create_directory(
                        work_root.name
                    )
                    invoke_live_start_fault(
                        fault_hook,
                        LiveStartFaultPoint.AFTER_TRANSITION_PRIMARY_ARTIFACT,
                    )
                bound_root = _session._thaw(pending)
                bound_root.pop("content_sha256", None)
                bound_root.update(
                    {
                        "stage": "PRIMARY_APPLIED",
                        "work_root_identity": work_identity,
                    }
                )
                current = _session._transition_receipt_authorized_under_lock(
                    session_lease=session_lease,
                    expected_session=current,
                    event="same_phase_cas",
                    changes={
                        "pending_transition": _session._seal_pending(
                            bound_root
                        )
                    },
                )
                pending = current.pending_transition
            if (
                not isinstance(pending, Mapping)
                or pending.get("stage") != "PRIMARY_APPLIED"
            ):
                raise SessionConflictError(
                    "live_start_prepublication_cursor_invalid"
                )
            work_identity = tuple(pending["work_root_identity"])
            with _hold_bound_materialized_work_root(
                work_parent_guard=work_parent_guard,
                work_root=work_root,
                expected_identity=work_identity,
            ) as work_root_guard:
                rendered_by_path = {
                    artifact.relative_path: artifact
                    for artifact in rendered.artifacts
                }
                cursor = int(pending["next_action_index"])
                for index in range(cursor, len(actions)):
                    action = actions[index]
                    artifact = rendered_by_path[str(action["relative_path"])]
                    created = _materialize_or_confirm_rendered_artifact(
                        work_root_guard=work_root_guard,
                        artifact=artifact,
                    )
                    if created:
                        invoke_live_start_fault(
                            fault_hook,
                            LiveStartFaultPoint.AFTER_TRANSITION_SECONDARY_ARTIFACT,
                        )
                    next_pending = _session._thaw(pending)
                    next_pending.pop("content_sha256", None)
                    next_pending["next_action_index"] = index + 1
                    current = _session._transition_receipt_authorized_under_lock(
                        session_lease=session_lease,
                        expected_session=current,
                        event="same_phase_cas",
                        changes={
                            "pending_transition": _session._seal_pending(
                                next_pending
                            )
                        },
                    )
                    pending = current.pending_transition
                    if not isinstance(pending, Mapping):
                        raise SessionConflictError("live_start_materialization_pending_missing")
                work_binding = _rebuild_prepublication_work_binding(
                    rendered=rendered,
                    work_parent=work_parent,
                    work_parent_identity=work_parent_identity,
                    work_root=work_root,
                    work_identity=work_identity,
                )
                current = _session._transition_receipt_authorized_under_lock(
                    session_lease=session_lease,
                    expected_session=current,
                    event="same_phase_cas",
                    changes={
                        "pending_transition": None,
                        "prepublication_work_binding": work_binding,
                    },
                )
                work_root_guard.validate()
            return current, work_root, work_identity, work_binding


def _prepublication_materialization_actions(
    rendered: RenderedConfigureRun,
) -> list[dict[str, Any]]:
    if render_configure_run_model(rendered.model) != rendered:
        raise ValueError("rendered_configure_run_invalid")
    return [
        {
            "relative_path": artifact.relative_path,
            "size": artifact.size,
            "sha256": "sha256:" + artifact.sha256,
        }
        for artifact in rendered.artifacts
    ]


@contextmanager
def _hold_bound_materialized_work_root(
    *,
    work_parent_guard: PlainDirectoryMutationGuard,
    work_root: Path,
    expected_identity: PathIdentity,
) -> Iterator[PlainDirectoryMutationGuard]:
    if work_root.parent != work_parent_guard.path:
        raise ValueError("live_start_prepublication_work_binding_changed")
    try:
        with work_parent_guard.hold_child_directory(
            work_root.name,
            expected_identity=expected_identity,
        ) as work_root_guard:
            yield work_root_guard
    except (FileNotFoundError, NotADirectoryError) as error:
        raise ValueError(
            "live_start_prepublication_work_identity_changed"
        ) from error
    except ValueError as error:
        if str(error) in {
            "filesystem_directory_identity_changed",
            "filesystem_path_identity_changed",
        }:
            raise ValueError(
                "live_start_prepublication_work_identity_changed"
            ) from error
        raise


def _materialize_or_confirm_rendered_artifact(
    *,
    work_root_guard: PlainDirectoryMutationGuard,
    artifact: Any,
) -> bool:
    parts = str(artifact.relative_path).split("/")
    with ExitStack() as stack:
        parent_guard = work_root_guard
        for part in parts[:-1]:
            try:
                status = parent_guard.child_status(part)
            except FileNotFoundError:
                identity = parent_guard.create_directory(part)
            else:
                if status_is_reparse(status) or not stat.S_ISDIR(
                    status.st_mode
                ):
                    raise ValueError(
                        "live_start_prepublication_work_tree_changed"
                    )
                identity = path_identity_from_status(status)
            parent_guard = stack.enter_context(
                parent_guard.hold_child_directory(
                    part,
                    expected_identity=identity,
                )
            )
        target = parent_guard.path / parts[-1]
        if path_lexists(target):
            status = plain_file_status(target)
            raw = read_file_no_follow(
                target,
                expected_status=status,
                maximum_size=max(1, artifact.size),
            )
            if raw != artifact.content:
                raise ValueError(
                    "live_start_prepublication_work_tree_changed"
                )
            parent_guard.validate()
            return False
        atomic_write_reserved_bytes(
            path=target,
            payload=artifact.content,
            expected_parent_identity=parent_guard.identity,
            expected_predecessor_identity=None,
            expected_predecessor_sha256=None,
            maximum_size=max(1, artifact.size),
        )
        status = plain_file_status(target)
        raw = read_file_no_follow(
            target,
            expected_status=status,
            maximum_size=max(1, artifact.size),
        )
        if raw != artifact.content:
            raise ValueError("live_start_prepublication_work_tree_changed")
        parent_guard.validate()
        return True


def _rebuild_prepublication_work_binding(
    *,
    rendered: RenderedConfigureRun,
    work_parent: Path,
    work_parent_identity: PathIdentity,
    work_root: Path,
    work_identity: PathIdentity,
) -> dict[str, Any]:
    if path_identity(work_root) != work_identity:
        raise ValueError("live_start_prepublication_work_identity_changed")
    snapshot = snapshot_bounded_filesystem_package(work_root)
    if _snapshot_files(snapshot) != {
        item.relative_path: item.content for item in rendered.artifacts
    }:
        raise ValueError("live_start_prepublication_work_tree_changed")
    cleanup_manifest_sha256, cleanup_entry_count = _cleanup_manifest(
        work_root
    )
    return {
        "work_parent_path": str(work_parent),
        "work_parent_identity": work_parent_identity,
        "work_root": str(work_root),
        "work_root_identity": work_identity,
        "work_tree_sha256": _snapshot_digest(snapshot),
        "cleanup_manifest_sha256": cleanup_manifest_sha256,
        "cleanup_entry_count": cleanup_entry_count,
    }


def _validate_and_install_package_receipt(
    *,
    rendered: RenderedConfigureRun,
    work_root: Path,
    work_binding: Mapping[str, Any],
    package_root: Path,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    fault_hook: LiveStartFaultHook,
    frozen_compiler_inputs: FrozenCompilerInputs | None = None,
) -> tuple[LiveStartSession, FrozenJsonDocument]:
    run_view = snapshot_bounded_filesystem_package(work_root)
    strict = validate_complete_configure_run_from_view(run_view)
    if not strict_validation_passed(strict):
        raise ValueError("live_start_strict_validation_failed")
    _emit_pipeline_event("strict_validated")
    package_view = snapshot_bounded_filesystem_package(package_root)
    stored_derivation = package_view.read_json(DERIVATION_RECEIPT_PATH)
    verified, reasons = verify_package_derivation_receipt_from_view(
        package_view,
        stored_derivation,
    )
    if not verified or reasons:
        raise ValueError("live_start_package_derivation_invalid")
    _emit_pipeline_event("derivation_replayed")
    operator_inputs = load_operator_summary_inputs(package_view)
    stored_operator = package_view.read_json("reports/operator_summary.json")
    if build_operator_summary_from_inputs(operator_inputs) != stored_operator:
        raise ValueError("live_start_operator_summary_parity_invalid")
    _emit_pipeline_event("operator_summary_recomputed")
    gate = evaluate_apply_gate(
        package_root, **({"frozen_compiler_inputs": frozen_compiler_inputs}
                         if frozen_compiler_inputs is not None else {}),
    )
    if gate.get("status") != "allowed":
        raise ValueError("live_start_apply_gate_blocked")
    package_digest = "sha256:" + rendered.model.package.compiled.deck_fingerprint
    rendered_package = rendered.model.package
    del rendered_package
    package_digest = _snapshot_digest(package_view)
    unsigned = {
        "run_id": current.run_id,
        "candidate_revision": current.candidate_revision,
        "input_snapshot_manifest_sha256": (
            current.input_snapshot_manifest_sha256
        ),
        "starter_context_sha256": current.artifact_bindings[
            "starter/starter_context.json"
        ],
        "candidate_sha256": current.artifact_bindings[
            "starter/starter_config_candidate.json"
        ],
        "review_sha256": current.artifact_bindings[
            "starter/starter_config_review.json"
        ],
        "package_root_sha256": package_digest,
        "derivation_receipt_sha256": _sha256_bytes(
            package_view.read_bytes(DERIVATION_RECEIPT_PATH)
        ),
        "operator_summary_sha256": _sha256_bytes(
            package_view.read_bytes("reports/operator_summary.json")
        ),
        "apply_gate_allowed": True,
        "prepublication_work_root": str(work_binding["work_root"]),
        "prepublication_work_parent_path": str(
            work_binding["work_parent_path"]
        ),
        "prepublication_work_parent_identity": work_binding[
            "work_parent_identity"
        ],
        "prepublication_work_root_identity": work_binding[
            "work_root_identity"
        ],
        "prepublication_work_tree_sha256": work_binding[
            "work_tree_sha256"
        ],
        "cleanup_manifest_sha256": work_binding[
            "cleanup_manifest_sha256"
        ],
        "cleanup_entry_count": work_binding["cleanup_entry_count"],
    }
    sealed = _session.seal_validation_receipt(
        receipt_kind="package_validation",
        unsigned_value=unsigned,
    )
    document = FrozenJsonDocument.from_value(dict(sealed))
    if current.phase is LiveStartPhase.REVIEW_APPROVED:
        current = _install_receipt_transition(
            session_lease=session_lease,
            current=current,
            operation="install_package_validation",
            target_phase=LiveStartPhase.PACKAGE_VALIDATED,
            event="package_validated",
            logical_path=_PACKAGE_RECEIPT_LOGICAL,
            document=document,
            additional_pending=dict(work_binding),
            event_changes={"prepublication_work_binding": dict(work_binding)},
            fault_hook=fault_hook,
            written_event="package_validation_receipt_written",
            committed_event="package_validated_cas",
        )
    else:
        _require_exact_receipt(
            session_lease.session_root / _PACKAGE_RECEIPT_LOGICAL,
            document.canonical_json,
        )
    return current, document


def _plan_and_install_prepublication_receipt(
    *,
    package_root: Path,
    package_root_sha256: str,
    runtime_root: Path,
    bound_date: str,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    fault_hook: LiveStartFaultHook,
    frozen_compiler_inputs: FrozenCompilerInputs | None = None,
) -> tuple[LiveStartSession, FrozenJsonDocument]:
    if current.phase is LiveStartPhase.PACKAGE_VALIDATED:
        planned = plan_apply_package(
            package_root=package_root,
            runtime_root=runtime_root,
            **({"frozen_compiler_inputs": frozen_compiler_inputs}
               if frozen_compiler_inputs is not None else {}),
        )
        planned["created_at_utc"] = f"{bound_date}T00:00:00+00:00"
        planned["diagnostic_only"] = True
        planned["package_root"] = str(package_root.resolve())
        planned["package_root_sha256"] = package_root_sha256
        document = FrozenJsonDocument.from_value(planned)
        _emit_pipeline_event("fake_apply_planned")
        current = _install_receipt_transition(
            session_lease=session_lease,
            current=current,
            operation="install_prepublication_validation",
            target_phase=LiveStartPhase.PREPUBLICATION_CHECK_PASSED,
            event="prepublication_passed",
            logical_path=_PREPUBLICATION_RECEIPT_LOGICAL,
            document=document,
            additional_pending={},
            event_changes={},
            fault_hook=fault_hook,
            written_event="diagnostic_receipt_written",
            committed_event="prepublication_check_passed_cas",
        )
    else:
        # A committed diagnostic is historical, not current Runtime authority.
        receipt_path = session_lease.session_root / _PREPUBLICATION_RECEIPT_LOGICAL
        raw = read_file_no_follow(
            receipt_path,
            expected_status=plain_file_status(receipt_path),
            maximum_size=_MAX_RECEIPT_BYTES,
        )
        if _sha256_bytes(raw) != current.artifact_bindings.get(
            _PREPUBLICATION_RECEIPT_LOGICAL
        ):
            raise ValueError("live_start_receipt_bytes_changed")
        document = FrozenJsonDocument(canonical_json=raw)
    return current, document


def _install_receipt_transition(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    operation: str,
    target_phase: LiveStartPhase,
    event: str,
    logical_path: str,
    document: FrozenJsonDocument,
    additional_pending: Mapping[str, Any],
    event_changes: Mapping[str, Any],
    fault_hook: LiveStartFaultHook,
    written_event: str,
    committed_event: str,
) -> LiveStartSession:
    receipt_path = session_lease.session_root / logical_path
    bindings = dict(current.artifact_bindings)
    bindings[logical_path] = _sha256_bytes(document.canonical_json)
    pending = current.pending_transition
    if pending is None:
        receipt_parent_path, receipt_parent_identity = (
            _capture_receipt_parent_binding(
                session_lease=session_lease,
                receipt_path=receipt_path,
            )
        )
        prepared = _session._empty_pending_transition(
            session=current,
            operation=operation,
            external_file_action=None,
        )
        prepared.update(additional_pending)
        prepared.update(
            {
                "receipt_parent_path": str(receipt_parent_path),
                "receipt_parent_identity": receipt_parent_identity,
            }
        )
        prepared["target_phase"] = target_phase.value
        prepared["successor_artifact_bindings"] = bindings
        current = _session._transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=current,
            event="same_phase_cas",
            changes={"pending_transition": _session._seal_pending(prepared)},
        )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_PENDING_TRANSITION_CAS,
        )
        pending = current.pending_transition
    if not isinstance(pending, Mapping) or pending.get("operation") != operation:
        raise SessionConflictError("live_start_receipt_transition_cursor_invalid")
    if (
        pending.get("receipt_parent_path") != str(receipt_path.parent)
        or pending.get("receipt_parent_identity") is None
    ):
        raise SessionCapabilityError(
            "live_start_receipt_parent_binding_changed"
        )
    if pending.get("stage") == "PREPARED":
        created = _write_or_confirm_receipt(
            path=receipt_path,
            payload=document.canonical_json,
            session_lease=session_lease,
            expected_parent_identity=tuple(
                pending["receipt_parent_identity"]
            ),
        )
        if created:
            _emit_pipeline_event(written_event)
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_TRANSITION_PRIMARY_ARTIFACT,
            )
        primary = _session._thaw(pending)
        primary.pop("content_sha256", None)
        primary["stage"] = "PRIMARY_APPLIED"
        current = _session._transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=current,
            event="same_phase_cas",
            changes={"pending_transition": _session._seal_pending(primary)},
        )
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.BEFORE_TRANSITION_PHASE_CAS,
    )
    changes = {
        "artifact_bindings": bindings,
        "pending_transition": None,
        **dict(event_changes),
    }
    current = _session._transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=current,
        event=event,
        changes=changes,
    )
    _emit_pipeline_event(committed_event)
    return current


def _capture_receipt_parent_binding(
    *,
    session_lease: LiveStartSessionLease,
    receipt_path: Path,
) -> tuple[Path, PathIdentity]:
    if (
        receipt_path.parent.parent != session_lease.session_root
        or receipt_path.parent.name != "receipts"
    ):
        raise SessionCapabilityError(
            "live_start_receipt_parent_binding_changed"
        )
    try:
        with hold_plain_directory(
            session_lease.session_root,
            expected_identity=session_lease.session_root_identity,
        ) as root_guard:
            with root_guard.hold_child_directory("receipts") as receipt_guard:
                root_guard.validate()
                receipt_guard.validate()
                return receipt_guard.path, receipt_guard.identity
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        raise SessionCapabilityError(
            "live_start_receipt_parent_binding_changed"
        ) from error


def _write_or_confirm_receipt(
    *,
    path: Path,
    payload: bytes,
    session_lease: LiveStartSessionLease,
    expected_parent_identity: PathIdentity,
) -> bool:
    if (
        path.parent.parent != session_lease.session_root
        or path.parent.name != "receipts"
    ):
        raise SessionCapabilityError(
            "live_start_receipt_parent_binding_changed"
        )
    try:
        with hold_plain_directory(
            session_lease.session_root,
            expected_identity=session_lease.session_root_identity,
        ) as root_guard:
            with root_guard.hold_child_directory(
                "receipts",
                expected_identity=expected_parent_identity,
            ) as receipt_guard:
                if path_lexists(path):
                    _require_exact_receipt(path, payload)
                    receipt_guard.validate()
                    return False
                atomic_write_reserved_bytes(
                    path=path,
                    payload=payload,
                    expected_parent_identity=expected_parent_identity,
                    expected_predecessor_identity=None,
                    expected_predecessor_sha256=None,
                    maximum_size=_MAX_RECEIPT_BYTES,
                )
                _require_exact_receipt(path, payload)
                receipt_guard.validate()
                return True
    except AtomicWriteConflictError as error:
        raise SessionCapabilityError(
            "live_start_receipt_parent_binding_changed"
        ) from error
    except (FileNotFoundError, NotADirectoryError, ValueError) as error:
        if str(error) == "live_start_receipt_bytes_changed":
            raise
        raise SessionCapabilityError(
            "live_start_receipt_parent_binding_changed"
        ) from error


def _require_exact_receipt(path: Path, payload: bytes) -> None:
    status = plain_file_status(path)
    raw = read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=_MAX_RECEIPT_BYTES,
    )
    if raw != payload:
        raise ValueError("live_start_receipt_bytes_changed")


def _snapshot_files(view: Any) -> dict[str, bytes]:
    return {name: view.read_bytes(name) for name in view.file_names()}


def _snapshot_digest(view: Any) -> str:
    framed = bytearray()
    for name in view.file_names():
        raw = view.read_bytes(name)
        framed.extend(name.encode("utf-8"))
        framed.extend(b"\0")
        framed.extend(str(len(raw)).encode("ascii"))
        framed.extend(b"\0")
        framed.extend(_sha256_bytes(raw).encode("ascii"))
        framed.extend(b"\0")
    return _sha256_bytes(bytes(framed))


def _snapshot_digest_from_cleanup_entries(
    entries: list[dict[str, Any]],
) -> str:
    framed = bytearray()
    for row in sorted(
        (
            row
            for row in entries
            if row["entry_kind"] == "file"
        ),
        key=lambda row: str(row["relative_path"]),
    ):
        framed.extend(str(row["relative_path"]).encode("utf-8"))
        framed.extend(b"\0")
        framed.extend(str(row["size"]).encode("ascii"))
        framed.extend(b"\0")
        framed.extend(str(row["sha256"]).encode("ascii"))
        framed.extend(b"\0")
    return _sha256_bytes(bytes(framed))


def _cleanup_manifest(work_root: Path) -> tuple[str, int]:
    entries = _cleanup_entries(work_root)
    canonical = _session._canonical_json(entries)
    return _sha256_bytes(canonical), len(entries)


def _cleanup_entries(work_root: Path) -> list[dict[str, Any]]:
    require_plain_directory(work_root)
    rows: list[dict[str, Any]] = []
    paths = [work_root, *work_root.rglob("*")]
    if len(paths) > _session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_ENTRIES:
        raise ValueError("live_start_cleanup_inventory_entry_count_invalid")
    for path in paths:
        status = path.lstat()
        if status_is_reparse(status):
            raise ValueError("live_start_cleanup_inventory_entry_unsafe")
        relative = (
            "." if path == work_root else path.relative_to(work_root).as_posix()
        )
        parent_identity = path_identity(path.parent)
        identity = path_identity_from_status(status)
        if stat.S_ISDIR(status.st_mode):
            entry_kind = "root" if path == work_root else "directory"
            size: int | None = None
            digest: str | None = None
        elif stat.S_ISREG(status.st_mode) and path != work_root:
            raw = read_file_no_follow(
                path,
                expected_status=status,
                maximum_size=_MAX_RECEIPT_BYTES * 1024,
            )
            entry_kind = "file"
            size = len(raw)
            digest = _sha256_bytes(raw)
        else:
            raise ValueError("live_start_cleanup_inventory_entry_unsafe")
        rows.append(
            {
                "relative_path": relative,
                "entry_kind": entry_kind,
                "identity": identity,
                "expected_parent_identity": parent_identity,
                "size": size,
                "sha256": digest,
            }
        )
    rows.sort(
        key=lambda row: (
            -(
                0
                if row["relative_path"] == "."
                else str(row["relative_path"]).count("/") + 1
            ),
            str(row["relative_path"]).encode("utf-8"),
        )
    )
    return rows


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def publish_validated_prepublication(
    *,
    validated: ValidatedPrepublication,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
) -> LiveStartSession:
    """Publish one validated package through the sealed owning capabilities."""

    return _publish_validated_prepublication(
        validated=validated,
        session_lease=session_lease,
        expected_session=expected_session,
        profile_lease=profile_lease,
        operation_lease=operation_lease,
        fault_hook=no_live_start_fault,
    )


def _require_publication_capabilities(
    *,
    validated: ValidatedPrepublication,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
) -> None:
    if (
        not isinstance(validated, ValidatedPrepublication)
        or not isinstance(session_lease, LiveStartSessionLease)
        or not isinstance(expected_session, LiveStartSession)
        or not isinstance(profile_lease, OperatorProfileLease)
        or not isinstance(operation_lease, OutputOperationAdmissionLease)
    ):
        raise SessionCapabilityError("live_start_publication_capability_invalid")


def _require_validated_prepublication_binding(
    *,
    validated: ValidatedPrepublication,
    current: LiveStartSession,
    session_lease: LiveStartSessionLease,
) -> None:
    try:
        work = current.prepublication_work_binding
        if (
            not isinstance(validated.rendered, RenderedConfigureRun)
            or not isinstance(validated.work_root, Path)
            or not isinstance(validated.package_root, Path)
            or not isinstance(validated.updated_session, LiveStartSession)
            or not isinstance(validated.work_root_identity, tuple)
            or validated.updated_session.content_sha256
            != current.content_sha256
            or validated.updated_session.canonical_json
            != current.canonical_json
            or not isinstance(work, Mapping)
            or validated.work_root != Path(str(work["work_root"]))
            or validated.work_root_identity
            != tuple(work["work_root_identity"])
            or validated.package_root
            != validated.work_root / "04_package"
            or not isinstance(
                validated.package_validation_receipt,
                FrozenJsonDocument,
            )
            or not isinstance(validated.diagnostic_receipt, FrozenJsonDocument)
        ):
            raise ValueError("validated_prepublication_value_mismatch")
        work_parent = Path(str(work["work_parent_path"]))
        with hold_plain_directory(
            work_parent,
            expected_identity=tuple(work["work_parent_identity"]),
        ) as work_parent_guard:
            with _hold_bound_materialized_work_root(
                work_parent_guard=work_parent_guard,
                work_root=validated.work_root,
                expected_identity=validated.work_root_identity,
            ):
                rebuilt = _rebuild_prepublication_work_binding(
                    rendered=validated.rendered,
                    work_parent=work_parent,
                    work_parent_identity=tuple(work["work_parent_identity"]),
                    work_root=validated.work_root,
                    work_identity=validated.work_root_identity,
                )
                if rebuilt != dict(work):
                    raise ValueError("validated_prepublication_work_mismatch")
                package_view = snapshot_bounded_filesystem_package(
                    validated.package_root
                )
                package_digest = _snapshot_digest(package_view)
        package_value = validated.package_validation_receipt.to_value()
        diagnostic_value = validated.diagnostic_receipt.to_value()
        if (
            not isinstance(package_value, dict)
            or not isinstance(diagnostic_value, dict)
            or package_value.get("package_root_sha256") != package_digest
            or diagnostic_value.get("package_root_sha256") != package_digest
            or diagnostic_value.get("package_root")
            != str(validated.package_root.resolve())
            or diagnostic_value.get("diagnostic_only") is not True
        ):
            raise ValueError("validated_prepublication_receipt_mismatch")
        for logical_path, document in (
            (_PACKAGE_RECEIPT_LOGICAL, validated.package_validation_receipt),
            (_PREPUBLICATION_RECEIPT_LOGICAL, validated.diagnostic_receipt),
        ):
            receipt_path = session_lease.session_root / logical_path
            _require_exact_receipt(receipt_path, document.canonical_json)
            if current.artifact_bindings.get(logical_path) != _sha256_bytes(
                document.canonical_json
            ):
                raise ValueError(
                    "validated_prepublication_artifact_binding_mismatch"
                )
        package_receipt = _session.validate_validation_receipt(
            receipt_kind="package_validation",
            value=package_value,
            run_id=current.run_id,
            candidate_revision=current.candidate_revision,
        )
        _session._require_completed_receipt_binding(
            session=current,
            receipt_kind="package_validation",
            receipt=package_receipt,
            receipt_bytes_sha256=_sha256_bytes(
                validated.package_validation_receipt.canonical_json
            ),
            receipt_logical_path=_PACKAGE_RECEIPT_LOGICAL,
        )
    except (
        AttributeError,
        KeyError,
        OSError,
        TypeError,
        ValueError,
        SessionConflictError,
    ) as error:
        raise SessionCapabilityError(
            "live_start_validated_prepublication_binding_mismatch"
        ) from error


def _revalidate_frozen_output_authority(
    *,
    validated: ValidatedPrepublication,
    current: LiveStartSession,
    profile_lease: OperatorProfileLease,
) -> tuple[dict[str, Any], Path, Path, PathIdentity | None]:
    _compiler, operator = _frozen_stage_bindings(validated.rendered.model)
    profile = revalidate_operator_profile_lease(profile_lease)
    output_base = Path(str(operator["output_base_root"]))
    output_child = output_base / str(operator["deck_output_name"])
    precondition = operator.get("deck_output_precondition")
    if not isinstance(precondition, dict):
        raise ValueError("live_start_output_precondition_invalid")
    predecessor = precondition.get("identity")
    predecessor_identity = None if predecessor is None else tuple(predecessor)
    if (
        profile.content_sha256 != operator["operator_profile_sha256"]
        or profile.runtime_root != Path(str(operator["runtime_root"]))
        or profile.runtime_root_identity
        != tuple(operator["runtime_root_identity"])
        or profile.output_base_root != output_base
        or profile.output_base_root_identity
        != tuple(operator["output_base_root_identity"])
        or profile_lease.profile is not profile
    ):
        raise ValueError("live_start_operator_profile_binding_changed")
    if path_identity(output_base) != profile.output_base_root_identity:
        raise ValueError("live_start_output_base_identity_changed")
    state = precondition.get("state")
    if state == "absent":
        if predecessor_identity is not None:
            raise ValueError("live_start_output_child_precondition_changed")
        if path_lexists(output_child):
            pending = current.pending_transition
            child = current.output_child_binding
            controlled_pending_create = (
                isinstance(pending, Mapping)
                and pending.get("operation") == "bootstrap_output_child"
                and pending.get("stage") == "PRIMARY_APPLIED"
                and pending.get("output_child_predecessor_state") == "absent"
                and pending.get("output_child_path") == str(output_child)
            )
            has_bound_child_authority = (
                isinstance(child, Mapping)
                and child.get("predecessor_state") == "absent"
                and child.get("output_child_path") == str(output_child)
            )
            if has_bound_child_authority and tuple(
                child.get("output_child_identity", ())
            ) != path_identity(output_child):
                raise ValueError("live_start_output_child_identity_changed")
            controlled_bound_child = has_bound_child_authority
            if not controlled_pending_create and not controlled_bound_child:
                raise ValueError(
                    "live_start_output_child_precondition_changed"
                )
    elif state == "existing":
        if predecessor_identity is None or not path_lexists(output_child):
            raise ValueError("live_start_output_child_precondition_changed")
        require_plain_directory(output_child)
        if path_identity(output_child) != predecessor_identity:
            raise ValueError("live_start_output_child_identity_changed")
    else:
        raise ValueError("live_start_output_precondition_invalid")
    return operator, output_base, output_child, predecessor_identity


def _require_current_session(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
) -> LiveStartSession:
    current = _session.load_live_start_session_under_lock(
        session_lease=session_lease
    )
    if current.content_sha256 != expected_session.content_sha256:
        raise SessionConflictError("live_start_publication_session_cursor_stale")
    return current


def load_bound_output_operation_admission(
    expected_session: LiveStartSession,
) -> OutputOperationAdmissionEvidence:
    """Project the exact persisted operation binding into physical evidence."""

    if not isinstance(expected_session, LiveStartSession):
        raise TypeError("live_start_session_required")
    binding = expected_session.output_operation_admission_binding
    if not isinstance(binding, Mapping):
        raise SessionConflictError(
            "live_start_output_operation_binding_missing"
        )
    validated = _session.validate_embedded_document(
        "output_operation_admission_binding",
        binding,
    )
    return OutputOperationAdmissionEvidence(
        admission_path=Path(str(validated["admission_path"])),
        admission_parent_identity=tuple(
            validated["admission_parent_identity"]
        ),
        admission_identity=tuple(validated["admission_identity"]),
        admission_size=int(validated["admission_size"]),
        admission_sha256=str(validated["admission_sha256"]),
        state="ACTIVE",
        run_id=str(validated["run_id"]),
        session_root=Path(str(validated["session_root"])),
        session_root_identity=tuple(validated["session_root_identity"]),
        expected_session_sha256=str(
            validated["expected_session_sha256"]
        ),
        operator_profile_path=Path(
            str(validated["operator_profile_path"])
        ),
        operator_profile_parent_identity=tuple(
            validated["operator_profile_parent_identity"]
        ),
        operator_profile_identity=tuple(
            validated["operator_profile_identity"]
        ),
        operator_profile_sha256=str(
            validated["operator_profile_sha256"]
        ),
        state_root_identity=tuple(validated["state_root_identity"]),
        output_base_root=Path(str(validated["output_base_root"])),
        output_base_root_identity=tuple(
            validated["output_base_root_identity"]
        ),
        output_child_path=Path(str(validated["output_child_path"])),
        output_child_predecessor_state=str(
            validated["output_child_predecessor_state"]
        ),
        output_child_predecessor_identity=(
            None
            if validated["output_child_predecessor_identity"] is None
            else tuple(validated["output_child_predecessor_identity"])
        ),
        output_bootstrap_lock_path=Path(
            str(validated["output_bootstrap_lock_path"])
        ),
        output_bootstrap_lock_identity=tuple(
            validated["output_bootstrap_lock_identity"]
        ),
        output_claim_path=Path(str(validated["output_claim_path"])),
    )


def authorize_output_operation_terminal_release_from_context(
    *,
    operation_lease: OutputOperationAdmissionLease,
    session_lease: LiveStartSessionLease,
    expected_terminal_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    expected: OutputOperationAdmissionEvidence,
) -> _session.OutputOperationAdmissionReleaseAuthorization:
    """Mint terminal release only from the exact held persisted context."""

    if not isinstance(expected, OutputOperationAdmissionEvidence):
        raise TypeError("output_operation_admission_evidence_required")
    current = _require_current_session(
        session_lease=session_lease,
        expected_session=expected_terminal_session,
    )
    profile = revalidate_operator_profile_lease(profile_lease)
    observed = observe_output_operation_admission_under_lease(operation_lease)
    bound = load_bound_output_operation_admission(current)
    binding = current.output_operation_admission_binding
    if (
        observed is None
        or replace(observed, admission_sha256=expected.admission_sha256) != expected
        or _publisher._admission_raw_sha256(observed) != expected.admission_sha256
        or bound != expected
        or not isinstance(binding, Mapping)
        or binding.get("state") != "TERMINAL_RELEASE_AUTHORIZED"
        or current.terminal_status is None
        or current.runtime_admission_binding is not None
        or profile.content_sha256 != expected.operator_profile_sha256
        or profile_lease.profile_path != expected.operator_profile_path
        or profile_lease.profile_parent_identity
        != expected.operator_profile_parent_identity
        or profile_lease.profile_identity != expected.operator_profile_identity
    ):
        raise SessionConflictError(
            "live_start_output_operation_terminal_release_invalid"
        )
    return _session._authorize_output_operation_admission_release_under_lock(
        session_lease=session_lease,
        expected_release_authorized_session=current,
    )


def _require_publication_resume_authority(
    *,
    run_model: ConfigureRunModel,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_root: Path,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
) -> tuple[
    LiveStartSession,
    Path,
    Path,
    OutputOperationAdmissionEvidence,
]:
    _require_prepublication_capabilities(
        run_model=run_model,
        session_lease=session_lease,
        expected_session=expected_session,
        runtime_root=runtime_root,
    )
    if not isinstance(
        profile_lease, OperatorProfileLease
    ) or not isinstance(operation_lease, OutputOperationAdmissionLease):
        raise SessionCapabilityError("live_start_publication_capability_invalid")
    compiler, operator = _frozen_stage_bindings(run_model)
    current = _session.validate_resume_under_lock(
        session_lease=session_lease,
        expected_deck_code_sha256=str(compiler["deck_code_sha256"]),
        expected_input_snapshot_manifest_sha256=(
            expected_session.input_snapshot_manifest_sha256
        ),
        expected_runtime_grammar_version=str(
            compiler["runtime_grammar_version"]
        ),
        expected_compiler_contract_id=str(compiler["compiler_contract_id"]),
    )
    if current.content_sha256 != expected_session.content_sha256:
        raise SessionConflictError("live_start_publication_session_cursor_stale")
    if current.phase is not LiveStartPhase.PUBLICATION_COMMITTED:
        raise SessionConflictError("live_start_publication_phase_invalid")
    profile = revalidate_operator_profile_lease(profile_lease)
    output_base = Path(str(operator["output_base_root"]))
    output_child = output_base / str(operator["deck_output_name"])
    if (
        Path(runtime_root).resolve(strict=True)
        != Path(str(operator["runtime_root"]))
        or path_identity(Path(runtime_root))
        != tuple(operator["runtime_root_identity"])
        or profile.content_sha256 != operator["operator_profile_sha256"]
        or profile.runtime_root != Path(str(operator["runtime_root"]))
        or profile.runtime_root_identity
        != tuple(operator["runtime_root_identity"])
        or profile.output_base_root != output_base
        or profile.output_base_root_identity
        != tuple(operator["output_base_root_identity"])
        or path_identity(output_base) != profile.output_base_root_identity
    ):
        raise ValueError("live_start_operator_profile_binding_changed")
    child = current.output_child_binding
    publication = current.publication_binding
    if (
        not isinstance(child, Mapping)
        or not isinstance(publication, Mapping)
        or child.get("output_child_path") != str(output_child)
        or tuple(child.get("output_child_identity", ()))
        != path_identity(output_child)
        or publication.get("output_child_path") != str(output_child)
        or tuple(publication.get("output_child_identity", ()))
        != path_identity(output_child)
    ):
        raise ValueError("live_start_output_child_binding_changed")
    evidence = observe_output_operation_admission_under_lease(operation_lease)
    binding = current.output_operation_admission_binding
    if (
        evidence is None
        or not isinstance(binding, Mapping)
        or binding.get("state") != "ACTIVE"
        or binding.get("admission_path") != str(evidence.admission_path)
        or tuple(binding.get("admission_parent_identity", ()))
        != evidence.admission_parent_identity
        or tuple(binding.get("admission_identity", ()))
        != evidence.admission_identity
        or binding.get("admission_size") != evidence.admission_size
        or binding.get("admission_sha256")
        != _publisher._admission_raw_sha256(evidence)
        or binding.get("run_id") != evidence.run_id
        or binding.get("session_root") != str(evidence.session_root)
        or tuple(binding.get("session_root_identity", ()))
        != evidence.session_root_identity
        or binding.get("operator_profile_sha256")
        != evidence.operator_profile_sha256
        or binding.get("output_base_root") != str(output_base)
        or tuple(binding.get("output_base_root_identity", ()))
        != path_identity(output_base)
        or binding.get("output_child_path") != str(output_child)
    ):
        raise ValueError("live_start_output_operation_binding_changed")
    return current, output_base, output_child, evidence


def _require_exact_current_publication(
    *, current: LiveStartSession, output_guard: PlainDirectoryMutationGuard,
) -> None:
    """Read back the exact session-owned publication; never repair its pointer."""
    publication = current.publication_binding
    child = current.output_child_binding
    operation = current.output_operation_admission_binding
    if not all(isinstance(item, Mapping) for item in (publication, child, operation)):
        raise SessionConflictError("live_start_publication_binding_missing")
    output_guard.validate()
    if (
        publication["output_child_path"] != str(output_guard.path)
        or tuple(publication["output_child_identity"]) != output_guard.identity
        or child["output_child_path"] != str(output_guard.path)
        or tuple(child["output_child_identity"]) != output_guard.identity
        or operation["state"] != "ACTIVE"
    ):
        raise SessionConflictError("live_start_publication_binding_changed")
    try:
        pointer, _view = _publisher._resolve_current_publication_without_ads(output_guard.path)
    except (OSError, ValueError) as error:
        raise SessionConflictError("live_start_publication_current_changed") from error
    if (
        pointer.revision != publication["revision"]
        or "sha256:" + pointer.content_root_sha256 != publication["content_root_sha256"]
    ):
        raise SessionConflictError("live_start_publication_current_changed")
    _publisher.validate_finalized_publication_authority(output_guard.path, pointer)
    owners = _publisher._load_valid_transactions(output_guard.path)
    if len(owners) != 1:
        raise SessionConflictError("live_start_publication_owner_changed")
    receipt = owners[0][1].live_start_commit_receipt
    if receipt is None:
        raise SessionConflictError("live_start_publication_receipt_binding_changed")
    predecessor = current.to_value()
    active_child = _session._thaw(child)
    active_child.pop("content_sha256")
    active_child.update(
        claim_state="ACTIVE", claim_identity=receipt.claim_identity,
        claim_sha256=receipt.claim_sha256,
    )
    active_child = _session.seal_embedded_document("output_child_binding", active_child)
    predecessor.update(
        phase=LiveStartPhase.PREPUBLICATION_CHECK_PASSED.value,
        pending_transition=None, publication_binding=None,
        result_intent=None, output_child_binding=active_child,
    )
    predecessor["prepublication_work_binding"].pop("cleanup_completion", None)
    predecessor_sha256 = _session._seal_session_value(
        predecessor, session_identity=None,
    ).content_sha256
    if (
        receipt.expected_session_sha256 != predecessor_sha256
        or receipt.operation_admission_identity != tuple(operation["admission_identity"])
        or receipt.operation_admission_sha256 != operation["admission_sha256"]
        or receipt.output_child_identity != output_guard.identity
        or receipt.pointer_predecessor_identity != publication["prior_current_identity"]
        or child["content_sha256"] != publication["output_child_binding_sha256"]
    ):
        raise SessionConflictError("live_start_publication_receipt_binding_changed")
    _publisher._require_current_pointer_receipt_exact(
        output_guard.path, receipt, _publisher.output_publication_bytes(pointer),
    )
    output_guard.validate()


def _resume_publication_committed(
    *,
    run_model: ConfigureRunModel,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_root: Path,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    current, output_base, output_child, operation_evidence = (
        _require_publication_resume_authority(
            run_model=run_model,
            session_lease=session_lease,
            expected_session=expected_session,
            runtime_root=runtime_root,
            profile_lease=profile_lease,
            operation_lease=operation_lease,
        )
    )
    child = current.output_child_binding
    if not isinstance(child, Mapping):
        raise SessionConflictError("live_start_output_child_binding_missing")
    with ExitStack() as stack:
        bootstrap_lease = None
        if child.get("claim_state") != "RETIRED":
            bootstrap_lease = stack.enter_context(
                _publisher.lease_output_child_bootstrap(
                    output_root=output_child
                )
            )
            binding = current.output_operation_admission_binding
            if (
                not isinstance(binding, Mapping)
                or bootstrap_lease.lock_path
                != Path(str(binding["output_bootstrap_lock_path"]))
                or bootstrap_lease.lock_identity
                != tuple(binding["output_bootstrap_lock_identity"])
            ):
                raise ValueError(
                    "live_start_output_bootstrap_capability_changed"
                )
        output_base_guard = stack.enter_context(
            hold_plain_directory(
                output_base,
                expected_identity=profile_lease.profile.output_base_root_identity,
            )
        )
        output_guard = stack.enter_context(
            hold_plain_directory(
                output_child,
                expected_identity=tuple(child["output_child_identity"]),
            )
        )
        if bootstrap_lease is not None:
            _publisher._finalize_committed_live_start_publication_under_guard(
                output_guard=output_guard,
                operation_lease=operation_lease,
                bootstrap_lease=bootstrap_lease,
                operation_admission=operation_evidence,
                session_lease=session_lease,
                expected_session=current,
                profile_lease=profile_lease,
            )
            current = _retire_output_child_claim(
                current=current,
                session_lease=session_lease,
                profile_lease=profile_lease,
                bootstrap_lease=bootstrap_lease,
                output_base_guard=output_base_guard,
                fault_hook=fault_hook,
            )
        if (
            observe_output_operation_admission_under_lease(operation_lease)
            != operation_evidence
        ):
            raise ValueError("live_start_output_operation_binding_changed")
        with ExclusiveFileLock(
            output_child / ".publish.lock",
            expected_parent_identity=output_guard.identity,
            path_guard=output_guard,
        ):
            _require_exact_current_publication(current=current, output_guard=output_guard)
        current = _continue_prepublication_cleanup(
            current=current,
            session_lease=session_lease,
            operation_lease=operation_lease,
            fault_hook=fault_hook,
        )
    revalidate_operator_profile_lease(profile_lease)
    observe_output_operation_admission_under_lease(operation_lease)
    return current


def _install_output_operation_admission(
    *,
    current: LiveStartSession,
    session_lease: LiveStartSessionLease,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: Any,
    output_base_guard: Any,
    output_child: Path,
    predecessor_identity: PathIdentity | None,
    fault_hook: LiveStartFaultHook,
) -> tuple[LiveStartSession, OutputOperationAdmissionEvidence]:
    pending = current.pending_transition
    if (
        current.output_operation_admission_binding is None
        and pending is None
        and observe_output_operation_admission_under_lease(operation_lease) is not None
    ):
        raise ValueError("live_start_output_operation_already_present")
    _publisher._require_runtime_live_admission_allows_output_mutation(output_child)
    if current.output_operation_admission_binding is None and pending is None:
        profile = profile_lease.profile
        planned = build_output_operation_admission_bytes(
            run_id=current.run_id,
            session_root=session_lease.session_root,
            session_root_identity=session_lease.session_root_identity,
            expected_session_sha256=current.content_sha256,
            operator_profile=profile,
            operator_profile_path=profile_lease.profile_path,
            operator_profile_parent_identity=(
                profile_lease.profile_parent_identity
            ),
            operator_profile_identity=profile_lease.profile_identity,
            state_root_identity=operation_lease.state_root_identity,
            output_base_root=output_base_guard.path,
            output_base_root_identity=output_base_guard.identity,
            output_child_path=output_child,
            output_child_predecessor_state=(
                "absent" if predecessor_identity is None else "existing"
            ),
            output_child_predecessor_identity=predecessor_identity,
            output_bootstrap_lock_path=bootstrap_lease.lock_path,
            output_bootstrap_lock_identity=bootstrap_lease.lock_identity,
            output_claim_path=output_child_claim_path(output_child),
        )
        current = _session.prepare_output_operation_admission_under_lock(
            session_lease=session_lease,
            expected_prepublication_session=current,
            admission_path=output_operation_admission_path(),
            admission_staging_path=output_operation_admission_staging_path(),
            admission_staging_inner_temp_path=(
                output_operation_admission_reserved_temp_path()
            ),
            admission_parent_identity=operation_lease.state_root_identity,
            planned_admission_size=len(planned),
            planned_admission_sha256=_sha256_bytes(planned),
            output_base_path=output_base_guard.path,
            output_base_identity=output_base_guard.identity,
            output_child_path=output_child,
            predecessor_output_child_identity=predecessor_identity,
            output_bootstrap_lock_path=bootstrap_lease.lock_path,
            output_bootstrap_lock_identity=bootstrap_lease.lock_identity,
        )
        _emit_pipeline_event("output_operation_admission_prepared_cas")
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_PREPARED,
        )

    for _attempt in range(6):
        pending = current.pending_transition
        if not isinstance(pending, Mapping) or pending.get("operation") != (
            "install_output_operation_admission"
        ):
            break
        stage = pending.get("stage")
        if stage == "PREPARED":
            external = pending["external_file_action"]
            action = (
                "retire_unbound_output_operation_admission_staging"
                if any(
                    path_lexists(Path(str(external[key])))
                    for key in ("staging_path", "inner_temp_path")
                )
                else "materialize_output_operation_admission_staging"
            )
            authorization = (
                _session.authorize_output_operation_admission_under_lock(
                    session_lease=session_lease,
                    expected_operation_session=current,
                    action=action,
                )
            )
            physical = _publisher.publish_output_operation_admission_under_lease(
                operation_lease=operation_lease,
                bootstrap_lease=bootstrap_lease,
                output_base_guard=output_base_guard,
                session_lease=session_lease,
                expected_operation_session=current,
                profile_lease=profile_lease,
                admission_authorization=authorization,
                fault_hook=fault_hook,
            )
            if action.startswith("retire_"):
                transition = "unbound_staging_retired"
            else:
                _emit_pipeline_event(
                    "output_operation_admission_staging_flushed"
                )
                transition = "staging_bound"
            current = _session.advance_output_operation_admission_under_lock(
                session_lease=session_lease,
                expected_operation_session=current,
                transition=transition,
                physical_step_receipt=physical.step_receipt,
            )
            if transition == "staging_bound":
                invoke_live_start_fault(
                    fault_hook,
                    LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_BOUND,
                )
            continue
        if stage == "STAGING_BOUND":
            authorization = (
                _session.authorize_output_operation_admission_under_lock(
                    session_lease=session_lease,
                    expected_operation_session=current,
                    action="commit_bound_output_operation_admission",
                )
            )
            physical = _publisher.publish_output_operation_admission_under_lease(
                operation_lease=operation_lease,
                bootstrap_lease=bootstrap_lease,
                output_base_guard=output_base_guard,
                session_lease=session_lease,
                expected_operation_session=current,
                profile_lease=profile_lease,
                admission_authorization=authorization,
                fault_hook=fault_hook,
            )
            _emit_pipeline_event("output_operation_admission_publish")
            current = _session.advance_output_operation_admission_under_lock(
                session_lease=session_lease,
                expected_operation_session=current,
                transition="admission_active",
                physical_step_receipt=physical.step_receipt,
            )
            _emit_pipeline_event("output_operation_admission_bound_cas")
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_BOUND,
            )
            break
        raise SessionConflictError("live_start_output_operation_cursor_invalid")

    evidence = observe_output_operation_admission_under_lease(operation_lease)
    binding = current.output_operation_admission_binding
    if (
        evidence is None
        or not isinstance(binding, Mapping)
        or binding.get("admission_identity") != evidence.admission_identity
        or binding.get("output_child_path") != str(output_child)
        or binding.get("state") != "ACTIVE"
    ):
        raise ValueError("live_start_output_operation_binding_changed")
    return current, evidence


def _bootstrap_output_child(
    *,
    current: LiveStartSession,
    session_lease: LiveStartSessionLease,
    profile_lease: OperatorProfileLease,
    bootstrap_lease: Any,
    output_base_guard: Any,
    output_child: Path,
    predecessor_identity: PathIdentity | None,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    pending = current.pending_transition
    if current.output_child_binding is None and pending is None:
        claim = build_output_child_claim_bytes(
            run_id=current.run_id,
            session_root=session_lease.session_root,
            session_root_identity=session_lease.session_root_identity,
            expected_session_sha256=current.content_sha256,
            output_base_path=output_base_guard.path,
            output_base_identity=output_base_guard.identity,
            output_child_path=output_child,
            predecessor_state=(
                "absent" if predecessor_identity is None else "existing"
            ),
            predecessor_output_child_identity=predecessor_identity,
        )
        current = _session.prepare_output_child_bootstrap_under_lock(
            session_lease=session_lease,
            expected_prepublication_session=current,
            output_base_path=output_base_guard.path,
            output_base_identity=output_base_guard.identity,
            output_child_path=output_child,
            predecessor_output_child_identity=predecessor_identity,
            planned_claim_size=len(claim),
            planned_claim_sha256=_sha256_bytes(claim),
            planned_claim_staging_path=(
                output_child_claim_staging_path(output_child)
            ),
            planned_claim_staging_inner_temp_path=(
                output_child_claim_staging_inner_temp_path(output_child)
            ),
            output_bootstrap_lock_path=bootstrap_lease.lock_path,
            output_bootstrap_lock_identity=bootstrap_lease.lock_identity,
        )
        _emit_pipeline_event("output_child_bootstrap_prepared_cas")
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_OUTPUT_CHILD_BOOTSTRAP_PREPARED,
        )

    for _attempt in range(7):
        pending = current.pending_transition
        if not isinstance(pending, Mapping) or pending.get("operation") != (
            "bootstrap_output_child"
        ):
            break
        stage = pending.get("stage")
        if stage == "PREPARED":
            external = pending["external_file_action"]
            action = (
                "retire_unbound_claim_staging"
                if any(
                    path_lexists(Path(str(external[key])))
                    for key in ("staging_path", "inner_temp_path")
                )
                else "materialize_claim_staging"
            )
            transition = (
                "unbound_claim_staging_retired"
                if action.startswith("retire_")
                else "claim_staging_bound"
            )
        elif stage == "STAGING_BOUND":
            action = "commit_bound_claim"
            transition = "claim_bound"
        elif stage == "PRIMARY_APPLIED":
            action = (
                "create_output_child"
                if predecessor_identity is None
                else "bind_existing_child"
            )
            transition = "child_bound"
        else:
            raise SessionConflictError("live_start_output_bootstrap_cursor_invalid")
        authorization = _session.authorize_output_child_bootstrap_under_lock(
            session_lease=session_lease,
            expected_bootstrap_session=current,
            action=action,
        )
        physical = _publisher.perform_output_child_bootstrap_step_under_guards(
            session_lease=session_lease,
            expected_bootstrap_session=current,
            profile_lease=profile_lease,
            bootstrap_lease=bootstrap_lease,
            output_base_guard=output_base_guard,
            bootstrap_authorization=authorization,
            fault_hook=fault_hook,
        )
        if action == "commit_bound_claim":
            _emit_pipeline_event("output_child_claim_publish")
        elif transition == "child_bound":
            _emit_pipeline_event(
                "output_child_created_or_confirmed",
                {
                    "disposition": (
                        "created"
                        if predecessor_identity is None
                        else "confirmed"
                    )
                },
            )
        current = _session.advance_output_child_bootstrap_under_lock(
            session_lease=session_lease,
            expected_bootstrap_session=current,
            transition=transition,
            bootstrap_authorization=None,
            physical_step_receipt=physical.step_receipt,
        )
        if transition == "claim_staging_bound":
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_STAGING_BOUND,
            )
        elif transition == "claim_bound":
            _emit_pipeline_event("output_child_claim_bound_cas")
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_BOUND,
            )
        elif transition == "child_bound":
            _emit_pipeline_event("output_child_bound_cas")
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_CHILD_BOUND,
            )
            break
    binding = current.output_child_binding
    if (
        not isinstance(binding, Mapping)
        or binding.get("claim_state") != "ACTIVE"
        or binding.get("output_child_path") != str(output_child)
    ):
        raise ValueError("live_start_output_child_binding_changed")
    return current


def _commit_publication(
    *,
    rendered: RenderedConfigureRun,
    current: LiveStartSession,
    session_lease: LiveStartSessionLease,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: Any,
    output_guard: Any,
    operation_evidence: OutputOperationAdmissionEvidence,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    if current.phase is LiveStartPhase.PUBLICATION_COMMITTED:
        return current
    try:
        authorization = (
            _publisher.authorize_output_publication_under_bootstrap_lease(
                operation_lease=operation_lease,
                bootstrap_lease=bootstrap_lease,
                output_guard=output_guard,
                operation_admission=operation_evidence,
                session_lease=session_lease,
                expected_session=current,
                profile_lease=profile_lease,
            )
        )
    except ValueError as error:
        if str(error) == "output_publication_claim_identity_changed":
            raise ValueError(
                "live_start_output_claim_identity_changed"
            ) from error
        raise
    with _publisher.publish_configure_run_under_guard(
        rendered,
        output_guard=output_guard,
        operation_lease=operation_lease,
        bootstrap_lease=bootstrap_lease,
        publication_authorization=authorization,
        fault_hook=no_fault,
    ) as published:
        prior_current_identity = (
            _publisher._live_start_publication_prior_current_identity(
                published
            )
        )
        _emit_pipeline_event("published")
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_PUBLICATION_COMMIT_BEFORE_OUTPUT_CHILD_CLAIM_RETIREMENT,
        )
        child = current.output_child_binding
        if not isinstance(child, Mapping):
            raise ValueError("live_start_output_child_binding_missing")
        publication_binding = {
            "output_child_path": str(output_guard.path),
            "output_child_identity": output_guard.identity,
            "output_child_binding_sha256": child["content_sha256"],
            "revision": f"revisions/{published.revision_root.name}",
            "content_root_sha256": (
                "sha256:" + published.content_root_sha256
            ),
            "prior_current_identity": prior_current_identity,
        }
        current = _session._transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=current,
            event="publication_committed",
            changes={"publication_binding": publication_binding},
        )
        _emit_pipeline_event("publication_committed_cas")
    return current


def _retire_output_child_claim(
    *,
    current: LiveStartSession,
    session_lease: LiveStartSessionLease,
    profile_lease: OperatorProfileLease,
    bootstrap_lease: Any,
    output_base_guard: Any,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    child = current.output_child_binding
    if not isinstance(child, Mapping):
        raise ValueError("live_start_output_child_binding_missing")
    if child.get("claim_state") == "RETIRED":
        return current
    if current.pending_transition is None:
        current = _session.prepare_output_child_claim_retirement_under_lock(
            session_lease=session_lease,
            expected_publication_session=current,
        )
        _emit_pipeline_event("output_child_claim_retirement_prepared")
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_RETIREMENT_PREPARED,
        )
    for _attempt in range(3):
        pending = current.pending_transition
        if not isinstance(pending, Mapping) or pending.get("operation") != (
            "retire_output_child_claim"
        ):
            break
        stage = pending.get("stage")
        if stage == "PREPARED":
            action = "retire_claim"
            transition = "claim_unlinked"
        elif stage == "PRIMARY_APPLIED":
            action = "confirm_claim_absent_and_current_exact"
            transition = "claim_retired"
        else:
            raise SessionConflictError(
                "live_start_output_claim_retirement_cursor_invalid"
            )
        authorization = _session.authorize_output_child_bootstrap_under_lock(
            session_lease=session_lease,
            expected_bootstrap_session=current,
            action=action,
        )
        physical = _publisher.perform_output_child_bootstrap_step_under_guards(
            session_lease=session_lease,
            expected_bootstrap_session=current,
            profile_lease=profile_lease,
            bootstrap_lease=bootstrap_lease,
            output_base_guard=output_base_guard,
            bootstrap_authorization=authorization,
            fault_hook=fault_hook,
        )
        _emit_pipeline_event(
            "output_child_claim_unlink"
            if transition == "claim_unlinked"
            else "output_child_claim_absence_current_confirmed"
        )
        current = _session.advance_output_child_bootstrap_under_lock(
            session_lease=session_lease,
            expected_bootstrap_session=current,
            transition=transition,
            bootstrap_authorization=None,
            physical_step_receipt=physical.step_receipt,
        )
        if transition == "claim_unlinked":
            _emit_pipeline_event("output_child_claim_unlink_cas")
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_UNLINK_CAS,
            )
        else:
            _emit_pipeline_event("output_child_claim_retired_cas")
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_RETIRED,
            )
            break
    return current


def _cleanup_parent(
    session_lease: LiveStartSessionLease,
    *,
    operation_lease: OutputOperationAdmissionLease,
    create_if_missing: bool,
) -> tuple[Path, PathIdentity]:
    state_root = session_lease.session_root.parent.parent
    if (
        not isinstance(operation_lease, OutputOperationAdmissionLease)
        or state_root != operation_lease.state_root
        or session_lease.session_root.parent != state_root / "runs"
    ):
        raise SessionCapabilityError(
            "live_start_cleanup_state_root_binding_changed"
        )
    try:
        observed_operation = observe_output_operation_admission_under_lease(
            operation_lease
        )
    except (RuntimeError, ValueError) as error:
        raise SessionCapabilityError(
            "live_start_cleanup_state_root_binding_changed"
        ) from error
    if (
        observed_operation is None
        or observed_operation.state_root_identity
        != operation_lease.state_root_identity
    ):
        raise SessionCapabilityError(
            "live_start_cleanup_state_root_binding_changed"
        )
    cleanup_parent = state_root / "cleanup"
    try:
        with hold_plain_directory(
            state_root,
            expected_identity=operation_lease.state_root_identity,
        ) as state_guard:
            if not path_lexists(cleanup_parent):
                if not create_if_missing:
                    raise ValueError(
                        "live_start_cleanup_parent_identity_changed"
                    )
                cleanup_identity = state_guard.create_directory("cleanup")
            else:
                require_plain_directory(cleanup_parent)
                cleanup_identity = path_identity(cleanup_parent)
            state_guard.validate()
    except (FileNotFoundError, NotADirectoryError) as error:
        raise SessionCapabilityError(
            "live_start_cleanup_state_root_binding_changed"
        ) from error
    except ValueError as error:
        if str(error) == "live_start_cleanup_parent_identity_changed":
            raise
        raise SessionCapabilityError(
            "live_start_cleanup_state_root_binding_changed"
        ) from error
    return cleanup_parent, cleanup_identity


def _require_cleanup_work_root_absent(
    *,
    work_parent_guard: PlainDirectoryMutationGuard,
    work_root: Path,
) -> None:
    if work_root.parent != work_parent_guard.path:
        raise ValueError("live_start_cleanup_work_binding_changed")
    try:
        work_parent_guard.child_status(work_root.name)
    except FileNotFoundError:
        return
    raise ValueError("live_start_cleanup_work_root_recreated")


def _require_cleanup_work_root_present(
    *,
    work_parent_guard: PlainDirectoryMutationGuard,
    work_root: Path,
    expected_identity: PathIdentity,
) -> None:
    if work_root.parent != work_parent_guard.path:
        raise ValueError("live_start_cleanup_work_binding_changed")
    try:
        status = work_parent_guard.child_status(work_root.name)
    except FileNotFoundError as error:
        raise ValueError("live_start_cleanup_work_root_identity_changed") from error
    if (
        status_is_reparse(status)
        or not stat.S_ISDIR(status.st_mode)
        or path_identity_from_status(status) != expected_identity
    ):
        raise ValueError("live_start_cleanup_work_root_identity_changed")
    work_parent_guard.validate()


@contextmanager
def _hold_cleanup_work_parent_binding(
    binding: Mapping[str, Any],
) -> Iterator[PlainDirectoryMutationGuard]:
    work_parent = Path(str(binding["work_parent_path"]))
    expected_identity = tuple(binding["work_parent_identity"])
    try:
        with hold_plain_directory(
            work_parent,
            expected_identity=expected_identity,
        ) as guard:
            guard.validate()
            yield guard
            guard.validate()
    except (FileNotFoundError, NotADirectoryError) as error:
        raise ValueError("live_start_cleanup_work_parent_identity_changed") from error
    except ValueError as error:
        if str(error) in {
            "filesystem_directory_invalid",
            "filesystem_path_identity_changed",
        }:
            raise ValueError(
                "live_start_cleanup_work_parent_identity_changed"
            ) from error
        raise


@contextmanager
def _hold_cleanup_parent_binding(
    cleanup_parent: Path,
    *,
    expected_identity: PathIdentity,
) -> Iterator[PlainDirectoryMutationGuard]:
    try:
        with hold_plain_directory(
            cleanup_parent,
            expected_identity=expected_identity,
        ) as guard:
            guard.validate()
            yield guard
            guard.validate()
    except (FileNotFoundError, NotADirectoryError) as error:
        raise ValueError("live_start_cleanup_parent_identity_changed") from error
    except ValueError as error:
        if str(error) in {
            "filesystem_directory_invalid",
            "filesystem_path_identity_changed",
        }:
            raise ValueError("live_start_cleanup_parent_identity_changed") from error
        raise


def _verified_cleanup_sha256(value: Any, *, error_reason: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise ValueError(error_reason)
    return value.removeprefix("sha256:")


def _build_cleanup_inventory(
    *,
    current: LiveStartSession,
    cleanup_parent: Path,
    cleanup_parent_identity: PathIdentity,
) -> tuple[bytes, dict[str, Any]]:
    work = current.prepublication_work_binding
    if not isinstance(work, Mapping):
        raise ValueError("live_start_prepublication_work_binding_missing")
    work_parent = Path(str(work["work_parent_path"]))
    work_root = Path(str(work["work_root"]))
    if (
        path_identity(work_parent) != tuple(work["work_parent_identity"])
        or path_identity(work_root) != tuple(work["work_root_identity"])
    ):
        raise ValueError("live_start_cleanup_work_parent_identity_changed")
    entries = _cleanup_entries(work_root)
    manifest_sha256 = _sha256_bytes(_session._canonical_json(entries))
    if (
        manifest_sha256 != work["cleanup_manifest_sha256"]
        or len(entries) != work["cleanup_entry_count"]
        or _snapshot_digest_from_cleanup_entries(entries)
        != work["work_tree_sha256"]
    ):
        raise ValueError("live_start_cleanup_work_inventory_changed")
    quarantine_path = cleanup_parent / f"live-start-{current.run_id}.quarantine"
    unsigned = {
        "schema_version": (
            _session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_SCHEMA_VERSION
        ),
        "inventory_kind": (
            _session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_KIND
        ),
        "run_id": current.run_id,
        "work_parent_path": str(work_parent),
        "work_parent_identity": work["work_parent_identity"],
        "work_root": str(work_root),
        "work_root_identity": work["work_root_identity"],
        "work_tree_sha256": work["work_tree_sha256"],
        "cleanup_manifest_sha256": manifest_sha256,
        "cleanup_entry_count": len(entries),
        "cleanup_parent_path": str(cleanup_parent),
        "cleanup_parent_identity": cleanup_parent_identity,
        "quarantine_path": str(quarantine_path),
        "entries": entries,
    }
    content_sha256 = _sha256_bytes(_session._canonical_json(unsigned))
    value = {**unsigned, "content_sha256": content_sha256}
    raw = _session._canonical_json(value)
    if len(raw) > _session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_BYTES:
        raise ValueError("live_start_cleanup_inventory_size_invalid")
    return raw, value


def _load_cleanup_inventory(
    raw: bytes,
    *,
    current: LiveStartSession,
    pending: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("live_start_cleanup_inventory_invalid") from error
    if not isinstance(value, dict) or _session._canonical_json(value) != raw:
        raise ValueError("live_start_cleanup_inventory_not_canonical")
    expected_fields = {
        "schema_version",
        "inventory_kind",
        "run_id",
        "work_parent_path",
        "work_parent_identity",
        "work_root",
        "work_root_identity",
        "work_tree_sha256",
        "cleanup_manifest_sha256",
        "cleanup_entry_count",
        "cleanup_parent_path",
        "cleanup_parent_identity",
        "quarantine_path",
        "entries",
        "content_sha256",
    }
    unsigned = dict(value)
    claimed = unsigned.pop("content_sha256", None)
    if (
        set(value) != expected_fields
        or value.get("schema_version")
        != _session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_SCHEMA_VERSION
        or value.get("inventory_kind")
        != _session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_KIND
        or value.get("run_id") != current.run_id
        or claimed != _sha256_bytes(_session._canonical_json(unsigned))
        or len(raw) != pending["cleanup_inventory_size"]
        or _sha256_bytes(raw) != pending["cleanup_inventory_sha256"]
        or value.get("cleanup_entry_count") != pending["cleanup_entry_count"]
        or value.get("cleanup_manifest_sha256")
        != pending["cleanup_manifest_sha256"]
        or value.get("work_root") != pending["work_root"]
        or tuple(value.get("work_root_identity", ()))
        != tuple(pending["work_root_identity"])
        or value.get("work_parent_path") != pending["work_parent_path"]
        or tuple(value.get("work_parent_identity", ()))
        != tuple(pending["work_parent_identity"])
        or tuple(value.get("cleanup_parent_identity", ()))
        != tuple(pending["cleanup_parent_identity"])
        or value.get("quarantine_path") != pending["quarantine_path"]
        or not isinstance(value.get("entries"), list)
        or len(value["entries"]) != pending["cleanup_entry_count"]
    ):
        raise ValueError("live_start_cleanup_inventory_binding_changed")
    return value


def _read_cleanup_inventory(
    *,
    current: LiveStartSession,
    pending: Mapping[str, Any],
) -> tuple[bytes, dict[str, Any], PathIdentity]:
    path = Path(str(pending["cleanup_inventory_path"]))
    status = plain_file_status(path)
    identity = path_identity_from_status(status)
    expected_identity = pending.get("cleanup_inventory_identity")
    if expected_identity is not None and identity != tuple(expected_identity):
        raise ValueError("live_start_cleanup_inventory_identity_changed")
    raw = read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=_session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_BYTES,
    )
    return raw, _load_cleanup_inventory(raw, current=current, pending=pending), identity


def _validate_quarantine_tree(
    *,
    quarantine: Path,
    inventory: Mapping[str, Any],
    cursor: int,
) -> None:
    entries = inventory["entries"]
    expected_remaining = {
        str(row["relative_path"]) for row in entries[cursor:]
    }
    actual_remaining: set[str] = set()
    if path_lexists(quarantine):
        require_plain_directory(quarantine)
        actual_remaining.add(".")
        actual_remaining.update(
            path.relative_to(quarantine).as_posix()
            for path in quarantine.rglob("*")
        )
    if actual_remaining != expected_remaining:
        raise ValueError("live_start_cleanup_unknown_or_missing_entry")
    for row in entries[cursor:]:
        relative = str(row["relative_path"])
        path = quarantine if relative == "." else quarantine / relative
        status = path.lstat()
        if (
            status_is_reparse(status)
            or path_identity_from_status(status) != tuple(row["identity"])
        ):
            raise ValueError("live_start_cleanup_entry_identity_changed")
        if relative != "." and path_identity(path.parent) != tuple(
            row["expected_parent_identity"]
        ):
            raise ValueError("live_start_cleanup_entry_parent_identity_changed")
        if row["entry_kind"] == "file":
            raw = read_file_no_follow(
                path,
                expected_status=status,
                maximum_size=_MAX_RECEIPT_BYTES * 1024,
            )
            if len(raw) != row["size"] or _sha256_bytes(raw) != row["sha256"]:
                raise ValueError("live_start_cleanup_entry_digest_changed")
        elif row["entry_kind"] not in {"directory", "root"} or not stat.S_ISDIR(
            status.st_mode
        ):
            raise ValueError("live_start_cleanup_entry_kind_changed")


def _remove_unbound_cleanup_path(
    path: Path,
    *,
    parent_identity: PathIdentity,
) -> None:
    if not path_lexists(path):
        return
    status = plain_file_status(path)
    read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=_session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_BYTES,
    )
    secure_unlink(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=parent_identity,
        missing_ok=False,
    )


def _advance_cleanup_cursor_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    pending: Mapping[str, Any],
    cursor: int,
) -> LiveStartSession:
    next_pending = _session._thaw(pending)
    next_pending.pop("content_sha256", None)
    next_pending["cleanup_cursor"] = cursor
    successor = _session._build_session_successor(
        current=current,
        update=_session.LiveStartSessionUpdate(
            event="same_phase_cas",
            changes={
                "pending_transition": _session._seal_pending(next_pending)
            },
        ),
        transition_authority=_session._INTERNAL_TRANSITION_AUTHORITY,
    )
    return _session._publish_session_successor_under_lock(
        session_lease=session_lease,
        current=current,
        successor=successor,
    )


def _continue_prepublication_cleanup(
    *,
    current: LiveStartSession,
    session_lease: LiveStartSessionLease,
    operation_lease: OutputOperationAdmissionLease,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    pending = current.pending_transition
    work = current.prepublication_work_binding
    completion = work.get("cleanup_completion") if isinstance(work, Mapping) else None
    cleanup_parent, observed_cleanup_parent_identity = _cleanup_parent(
        session_lease,
        operation_lease=operation_lease,
        create_if_missing=pending is None and completion is None,
    )
    if pending is None:
        work_binding = current.prepublication_work_binding
        cleanup_parent_identity = (
            tuple(completion["cleanup_parent_identity"])
            if isinstance(completion, Mapping) else observed_cleanup_parent_identity
        )
        if isinstance(completion, Mapping) and completion["cleanup_parent_path"] != str(cleanup_parent):
            raise ValueError("live_start_cleanup_parent_identity_changed")
    elif isinstance(pending, Mapping) and pending.get("operation") == (
        "cleanup_prepublication"
    ):
        work_binding = pending
        cleanup_parent_identity = tuple(pending["cleanup_parent_identity"])
    else:
        raise SessionConflictError("live_start_cleanup_cursor_invalid")
    if not isinstance(work_binding, Mapping):
        raise ValueError("live_start_prepublication_work_binding_missing")
    with _hold_cleanup_parent_binding(
        cleanup_parent,
        expected_identity=cleanup_parent_identity,
    ) as cleanup_parent_guard:
        with _hold_cleanup_work_parent_binding(work_binding) as work_parent_guard:
            return _continue_prepublication_cleanup_under_guards(
                current=current,
                session_lease=session_lease,
                fault_hook=fault_hook,
                cleanup_parent=cleanup_parent,
                cleanup_parent_identity=cleanup_parent_identity,
                cleanup_parent_guard=cleanup_parent_guard,
                work_parent_guard=work_parent_guard,
            )


def _continue_prepublication_cleanup_under_guards(
    *,
    current: LiveStartSession,
    session_lease: LiveStartSessionLease,
    fault_hook: LiveStartFaultHook,
    cleanup_parent: Path,
    cleanup_parent_identity: PathIdentity,
    cleanup_parent_guard: PlainDirectoryMutationGuard,
    work_parent_guard: PlainDirectoryMutationGuard,
) -> LiveStartSession:
    pending = current.pending_transition
    planned_inventory: tuple[bytes, dict[str, Any]] | None = None
    quarantine_preflight_complete = False
    if pending is None:
        work = current.prepublication_work_binding
        if not isinstance(work, Mapping):
            raise SessionConflictError("live_start_prepublication_work_binding_missing")
        work_root = Path(str(work["work_root"]))
        if current.phase is LiveStartPhase.PUBLICATION_COMMITTED and "cleanup_completion" in work:
            _session._validate_prepublication_work_binding(work)
            completion = work["cleanup_completion"]
            if (
                completion["cleanup_parent_path"] != str(cleanup_parent)
                or tuple(completion["cleanup_parent_identity"]) != cleanup_parent_identity
            ):
                raise ValueError("live_start_cleanup_parent_identity_changed")
            inventory_path = cleanup_parent / f"live-start-{current.run_id}.inventory.json"
            staging_path = inventory_path.with_name(inventory_path.name + ".staged")
            completed_surfaces = (
                inventory_path,
                staging_path,
                staging_path.with_name("." + staging_path.name + ".live-start-atomic.tmp"),
                cleanup_parent / f"live-start-{current.run_id}.quarantine",
            )
            cleanup_parent_guard.validate()
            work_parent_guard.validate()
            _require_cleanup_work_root_absent(work_parent_guard=work_parent_guard, work_root=work_root)
            if any(path_lexists(path) for path in completed_surfaces):
                raise ValueError("live_start_cleanup_foreign_residue_present")
            return current
        _require_cleanup_work_root_present(
            work_parent_guard=work_parent_guard,
            work_root=work_root,
            expected_identity=tuple(work["work_root_identity"]),
        )
        raw, inventory = _build_cleanup_inventory(
            current=current,
            cleanup_parent=cleanup_parent,
            cleanup_parent_identity=cleanup_parent_identity,
        )
        inventory_path = Path(str(inventory["cleanup_parent_path"])) / (
            f"live-start-{current.run_id}.inventory.json"
        )
        staging_path = inventory_path.with_name(inventory_path.name + ".staged")
        inner_path = staging_path.with_name(
            "." + staging_path.name + ".live-start-atomic.tmp"
        )
        quarantine_path = Path(str(inventory["quarantine_path"]))
        if any(
            path_lexists(path)
            for path in (inventory_path, staging_path, inner_path, quarantine_path)
        ):
            raise ValueError("live_start_cleanup_foreign_residue_present")
        external = _session._build_external_file_action(
            action_kind=(
                "materialize_prepublication_cleanup_inventory_staging"
            ),
            action_index=0,
            final_path=inventory_path,
            staging_path=staging_path,
            inner_temp_path=inner_path,
            parent_identity=cleanup_parent_identity,
            predecessor_identity=None,
            predecessor_size=None,
            predecessor_sha256=None,
            planned_successor_size=len(raw),
            planned_successor_sha256=_sha256_bytes(raw),
            commit_mode="create_no_replace",
        )
        work = current.prepublication_work_binding
        if not isinstance(work, Mapping):
            raise SessionConflictError("live_start_prepublication_work_binding_missing")
        prepared = _session._empty_pending_transition(
            session=current,
            operation="cleanup_prepublication",
            external_file_action=external,
        )
        prepared.update(
            {
                **dict(work),
                "cleanup_inventory_path": str(inventory_path),
                "cleanup_inventory_identity": None,
                "cleanup_inventory_size": len(raw),
                "cleanup_inventory_sha256": _sha256_bytes(raw),
                "quarantine_path": str(quarantine_path),
                "cleanup_parent_identity": cleanup_parent_identity,
                "quarantine_identity": None,
                "cleanup_cursor": 0,
            }
        )
        planned_inventory = raw, inventory
        current = _session._transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=current,
            event="same_phase_cas",
            changes={"pending_transition": _session._seal_pending(prepared)},
        )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_PENDING_TRANSITION_CAS,
        )

    for _attempt in range(6):
        pending = current.pending_transition
        if not isinstance(pending, Mapping) or pending.get("operation") != (
            "cleanup_prepublication"
        ):
            break
        stage = pending["stage"]
        if tuple(pending["cleanup_parent_identity"]) != cleanup_parent_identity:
            raise ValueError("live_start_cleanup_parent_identity_changed")
        cleanup_parent_guard.validate()
        work_parent_guard.validate()
        if stage in {"PREPARED", "STAGING_BOUND"} and path_lexists(
            Path(str(pending["quarantine_path"]))
        ):
            raise ValueError("live_start_cleanup_foreign_residue_present")
        if stage in {"PREPARED", "STAGING_BOUND"}:
            _require_cleanup_work_root_present(
                work_parent_guard=work_parent_guard,
                work_root=Path(str(pending["work_root"])),
                expected_identity=tuple(pending["work_root_identity"]),
            )
        elif stage == "CLEANUP_DELETING":
            _require_cleanup_work_root_absent(
                work_parent_guard=work_parent_guard,
                work_root=Path(str(pending["work_root"])),
            )
        if stage == "PREPARED":
            external = pending["external_file_action"]
            final_path = Path(str(external["final_path"]))
            staging_path = Path(str(external["staging_path"]))
            inner_path = Path(str(external["inner_temp_path"]))
            if path_lexists(final_path):
                raise ValueError("live_start_cleanup_direct_final_invalid")
            if path_lexists(staging_path) or path_lexists(inner_path):
                _remove_unbound_cleanup_path(
                    inner_path,
                    parent_identity=cleanup_parent_identity,
                )
                _remove_unbound_cleanup_path(
                    staging_path,
                    parent_identity=cleanup_parent_identity,
                )
                invoke_live_start_fault(
                    fault_hook,
                    LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_UNBOUND_STAGING_RETIRE_BEFORE_CAS,
                )
                next_external = _session._retire_unbound_external_from_receipt(
                    external=external,
                    next_action_kind=(
                        "materialize_prepublication_cleanup_inventory_staging"
                    ),
                )
                next_pending = _session._thaw(pending)
                next_pending.pop("content_sha256", None)
                next_pending["external_file_action"] = next_external
                current = _session._transition_receipt_authorized_under_lock(
                    session_lease=session_lease,
                    expected_session=current,
                    event="same_phase_cas",
                    changes={
                        "pending_transition": _session._seal_pending(next_pending)
                    },
                )
                continue
            if planned_inventory is None:
                raw, rebuilt = _build_cleanup_inventory(
                    current=current,
                    cleanup_parent=cleanup_parent,
                    cleanup_parent_identity=cleanup_parent_identity,
                )
            else:
                raw, rebuilt = planned_inventory
            if (
                len(raw) != pending["cleanup_inventory_size"]
                or _sha256_bytes(raw) != pending["cleanup_inventory_sha256"]
                or rebuilt["cleanup_manifest_sha256"]
                != pending["cleanup_manifest_sha256"]
            ):
                raise ValueError("live_start_cleanup_inventory_plan_changed")

            def materialized_fault(point: str) -> None:
                if point != "after_staging_flush_before_identity_return":
                    raise ValueError("live_start_cleanup_inventory_fault_invalid")
                invoke_live_start_fault(
                    fault_hook,
                    LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS,
                )

            materialized = atomic_materialize_staging_bytes(
                staging_path=staging_path,
                inner_temp_path=inner_path,
                payload=raw,
                expected_parent_identity=cleanup_parent_identity,
                maximum_size=(
                    _session.LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_BYTES
                ),
                fault_hook=materialized_fault,
            )
            _emit_pipeline_event(
                "prepublication_cleanup_inventory_staging_flushed"
            )
            bound = _session._thaw(
                _session._bind_external_staging_from_receipt(
                    external=external,
                    evidence={
                        "staging_identity": materialized.identity,
                        "staging_size": materialized.size,
                        "staging_sha256": materialized.sha256,
                    },
                )
            )
            bound.pop("content_sha256", None)
            bound["action_kind"] = (
                "commit_bound_prepublication_cleanup_inventory"
            )
            next_pending = _session._thaw(pending)
            next_pending.pop("content_sha256", None)
            next_pending["stage"] = "STAGING_BOUND"
            next_pending["external_file_action"] = (
                _session.seal_embedded_document("external_file_action", bound)
            )
            current = _session._transition_receipt_authorized_under_lock(
                session_lease=session_lease,
                expected_session=current,
                event="same_phase_cas",
                changes={"pending_transition": _session._seal_pending(next_pending)},
            )
            _emit_pipeline_event(
                "prepublication_cleanup_inventory_staging_bound_cas"
            )
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_BOUND,
            )
            continue
        if stage == "STAGING_BOUND":
            external = pending["external_file_action"]

            def committed_fault(point: str) -> None:
                if point == "after_bound_staging_posix_link_before_unlink":
                    invoke_live_start_fault(
                        fault_hook,
                        LiveStartFaultPoint.AFTER_BOUND_STAGING_POSIX_LINK_BEFORE_UNLINK,
                    )
                elif point == "after_bound_staging_commit_before_return":
                    invoke_live_start_fault(
                        fault_hook,
                        LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS,
                    )
                else:
                    raise ValueError(
                        "live_start_cleanup_inventory_fault_invalid"
                    )

            try:
                committed = atomic_commit_bound_staging_no_replace(
                    path=Path(str(external["final_path"])),
                    staging_path=Path(str(external["staging_path"])),
                    expected_staging_identity=tuple(
                        external["staging_identity"]
                    ),
                    expected_size=int(external["staging_size"]),
                    expected_sha256=str(external["staging_sha256"]),
                    expected_parent_identity=cleanup_parent_identity,
                    fault_hook=committed_fault,
                )
            except AtomicWriteConflictError as error:
                raise ValueError(
                    "live_start_cleanup_inventory_identity_changed"
                ) from error
            _emit_pipeline_event(
                "prepublication_cleanup_inventory_bound_commit"
            )
            next_pending = _session._thaw(pending)
            next_pending.pop("content_sha256", None)
            next_pending.update(
                {
                    "stage": "PRIMARY_APPLIED",
                    "external_file_action": None,
                    "cleanup_inventory_identity": committed.identity,
                    "quarantine_identity": None,
                    "cleanup_cursor": 0,
                }
            )
            current = _session._transition_receipt_authorized_under_lock(
                session_lease=session_lease,
                expected_session=current,
                event="same_phase_cas",
                changes={"pending_transition": _session._seal_pending(next_pending)},
            )
            _emit_pipeline_event(
                "prepublication_cleanup_inventory_primary_applied_cas"
            )
            continue
        if stage == "PRIMARY_APPLIED":
            _raw, inventory, _identity = _read_cleanup_inventory(
                current=current,
                pending=pending,
            )
            work_root = Path(str(pending["work_root"]))
            work_parent = Path(str(pending["work_parent_path"]))
            quarantine = Path(str(pending["quarantine_path"]))
            if path_identity(work_parent) != tuple(
                pending["work_parent_identity"]
            ):
                raise ValueError("live_start_cleanup_work_parent_identity_changed")
            if path_lexists(work_root) and not path_lexists(quarantine):
                if _session._canonical_json(
                    _cleanup_entries(work_root)
                ) != _session._canonical_json(inventory["entries"]):
                    raise ValueError("live_start_cleanup_inventory_tree_changed")
                secure_replace(
                    work_root,
                    quarantine,
                    expected_source_identity=tuple(pending["work_root_identity"]),
                    expected_source_parent_identity=tuple(
                        pending["work_parent_identity"]
                    ),
                    expected_target_parent_identity=cleanup_parent_identity,
                    expected_target_absent=True,
                )
            elif path_lexists(work_root) or not path_lexists(quarantine):
                raise ValueError("live_start_cleanup_quarantine_state_invalid")
            if (
                path_lexists(work_root)
                or not path_lexists(quarantine)
                or path_identity(quarantine)
                != tuple(pending["work_root_identity"])
            ):
                raise ValueError("live_start_cleanup_quarantine_state_invalid")
            cleanup_parent_guard.validate()
            work_parent_guard.validate()
            _require_cleanup_work_root_absent(
                work_parent_guard=work_parent_guard,
                work_root=work_root,
            )
            _validate_quarantine_tree(
                quarantine=quarantine,
                inventory=inventory,
                cursor=0,
            )
            quarantine_preflight_complete = True
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_PREPUBLICATION_QUARANTINE,
            )
            _emit_pipeline_event("prepublication_quarantine")
            next_pending = _session._thaw(pending)
            next_pending.pop("content_sha256", None)
            next_pending.update(
                {
                    "stage": "CLEANUP_DELETING",
                    "quarantine_identity": pending["work_root_identity"],
                    "cleanup_cursor": 0,
                }
            )
            cleanup_parent_guard.validate()
            work_parent_guard.validate()
            _require_cleanup_work_root_absent(
                work_parent_guard=work_parent_guard,
                work_root=work_root,
            )
            current = _session._transition_receipt_authorized_under_lock(
                session_lease=session_lease,
                expected_session=current,
                event="same_phase_cas",
                changes={
                    "pending_transition": _session._seal_pending(next_pending)
                },
            )
            continue
        if stage == "CLEANUP_DELETING":
            break
        raise SessionConflictError("live_start_cleanup_cursor_invalid")

    pending = current.pending_transition
    if not isinstance(pending, Mapping) or pending.get("stage") != (
        "CLEANUP_DELETING"
    ):
        raise SessionConflictError("live_start_cleanup_cursor_invalid")
    inventory_path = Path(str(pending["cleanup_inventory_path"]))
    if int(pending["cleanup_cursor"]) < int(pending["cleanup_entry_count"]):
        _raw, inventory, _identity = _read_cleanup_inventory(
            current=current,
            pending=pending,
        )
    else:
        inventory = None
    first_cleanup_action = True
    while int(pending["cleanup_cursor"]) < int(pending["cleanup_entry_count"]):
        if inventory is None:
            raise SessionConflictError("live_start_cleanup_inventory_missing")
        cleanup_parent_guard.validate()
        work_parent_guard.validate()
        _require_cleanup_work_root_absent(
            work_parent_guard=work_parent_guard,
            work_root=Path(str(pending["work_root"])),
        )
        cursor = int(pending["cleanup_cursor"])
        quarantine = Path(str(pending["quarantine_path"]))
        row = inventory["entries"][cursor]
        relative = str(row["relative_path"])
        target = quarantine if relative == "." else quarantine / relative
        target_present = path_lexists(target)
        if first_cleanup_action and not quarantine_preflight_complete:
            _validate_quarantine_tree(
                quarantine=quarantine,
                inventory=inventory,
                cursor=cursor if target_present else cursor + 1,
            )
        elif not target_present:
            raise ValueError("live_start_cleanup_unknown_or_missing_entry")
        if target_present:
            if row["entry_kind"] == "file":
                try:
                    secure_unlink_verified(
                        target,
                        expected_identity=tuple(row["identity"]),
                        expected_parent_identity=tuple(
                            row["expected_parent_identity"]
                        ),
                        expected_size=int(row["size"]),
                        expected_sha256=_verified_cleanup_sha256(
                            row["sha256"],
                            error_reason=(
                                "live_start_cleanup_entry_digest_changed"
                            ),
                        ),
                    )
                except ValueError as error:
                    raise ValueError(
                        "live_start_cleanup_entry_digest_changed"
                    ) from error
            else:
                expected_parent = (
                    cleanup_parent_identity
                    if relative == "."
                    else tuple(row["expected_parent_identity"])
                )
                try:
                    secure_rmdir_verified(
                        target,
                        expected_identity=tuple(row["identity"]),
                        expected_parent_identity=expected_parent,
                    )
                except ValueError as error:
                    raise ValueError(
                        "live_start_cleanup_entry_identity_changed"
                    ) from error
        if path_lexists(target):
            raise ValueError("live_start_cleanup_entry_delete_failed")
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_ENTRY,
        )
        cleanup_parent_guard.validate()
        work_parent_guard.validate()
        _require_cleanup_work_root_absent(
            work_parent_guard=work_parent_guard,
            work_root=Path(str(pending["work_root"])),
        )
        current = _advance_cleanup_cursor_under_lock(
            session_lease=session_lease,
            current=current,
            pending=pending,
            cursor=cursor + 1,
        )
        pending = current.pending_transition
        if not isinstance(pending, Mapping):
            raise SessionConflictError("live_start_cleanup_pending_missing")
        first_cleanup_action = False

    staging_path = inventory_path.with_name(inventory_path.name + ".staged")
    inner_temp_path = staging_path.with_name(
        "." + staging_path.name + ".live-start-atomic.tmp"
    )
    quarantine_path = Path(str(pending["quarantine_path"]))
    final_cleanup_surfaces = (
        inventory_path,
        staging_path,
        inner_temp_path,
        quarantine_path,
    )
    cleanup_parent_guard.validate()
    work_parent_guard.validate()
    _require_cleanup_work_root_absent(
        work_parent_guard=work_parent_guard,
        work_root=Path(str(pending["work_root"])),
    )
    inventory_deleted = path_lexists(inventory_path)
    if inventory_deleted:
        raw, _inventory, _identity = _read_cleanup_inventory(
            current=current,
            pending=pending,
        )
        if len(raw) != pending["cleanup_inventory_size"]:
            raise ValueError("live_start_cleanup_inventory_size_changed")
        try:
            secure_unlink_verified(
                inventory_path,
                expected_identity=tuple(pending["cleanup_inventory_identity"]),
                expected_parent_identity=cleanup_parent_identity,
                expected_size=int(pending["cleanup_inventory_size"]),
                expected_sha256=_verified_cleanup_sha256(
                    pending["cleanup_inventory_sha256"],
                    error_reason="live_start_cleanup_inventory_digest_changed",
                ),
            )
        except ValueError as error:
            raise ValueError(
                "live_start_cleanup_inventory_digest_changed"
            ) from error
    if any(path_lexists(path) for path in final_cleanup_surfaces):
        raise ValueError("live_start_cleanup_final_surface_present")
    if inventory_deleted:
        _emit_pipeline_event("prepublication_cleanup_inventory_deleted")
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE,
        )
        cleanup_parent_guard.validate()
        work_parent_guard.validate()
        _require_cleanup_work_root_absent(
            work_parent_guard=work_parent_guard,
            work_root=Path(str(pending["work_root"])),
        )
    if any(path_lexists(path) for path in final_cleanup_surfaces):
        raise ValueError("live_start_cleanup_final_surface_present")
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS,
    )
    cleanup_parent_guard.validate()
    work_parent_guard.validate()
    _require_cleanup_work_root_absent(
        work_parent_guard=work_parent_guard,
        work_root=Path(str(pending["work_root"])),
    )
    if any(path_lexists(path) for path in final_cleanup_surfaces):
        raise ValueError("live_start_cleanup_final_surface_present")
    current = _session._transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=current,
        event="same_phase_cas",
        changes={
            "pending_transition": None,
            "prepublication_work_binding": _session._completed_prepublication_work_binding(
                current.prepublication_work_binding, pending,
            ),
        },
    )
    _emit_pipeline_event("prepublication_cleanup_complete_cas")
    return current


def _publish_validated_prepublication(
    *,
    validated: ValidatedPrepublication,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    _require_publication_capabilities(
        validated=validated,
        session_lease=session_lease,
        expected_session=expected_session,
        profile_lease=profile_lease,
        operation_lease=operation_lease,
    )
    current = _require_current_session(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    if current.phase is not LiveStartPhase.PREPUBLICATION_CHECK_PASSED:
        raise SessionConflictError("live_start_publication_phase_invalid")
    _require_validated_prepublication_binding(
        validated=validated,
        current=current,
        session_lease=session_lease,
    )
    _emit_pipeline_event("profile_lease_enter")
    operator, output_base, output_child, predecessor_identity = (
        _revalidate_frozen_output_authority(
            validated=validated,
            current=current,
            profile_lease=profile_lease,
        )
    )
    del operator
    _emit_pipeline_event("profile_rebound_under_lease")
    _emit_pipeline_event("output_precondition_rebound")
    _emit_pipeline_event("output_operation_lock_enter")
    _publisher._bootstrap_neutral_output_locks(output_root=output_child)
    bootstrap_stack = ExitStack()
    bootstrap_lease = bootstrap_stack.enter_context(
        _publisher.lease_output_child_bootstrap(output_root=output_child)
    )
    try:
        _emit_pipeline_event("output_child_bootstrap_lock_enter")
        with hold_plain_directory(
            output_base,
            expected_identity=profile_lease.profile.output_base_root_identity,
        ) as output_base_guard:
            _emit_pipeline_event("output_base_identity_lease_enter")
            current, operation_evidence = _install_output_operation_admission(
                current=current,
                session_lease=session_lease,
                profile_lease=profile_lease,
                operation_lease=operation_lease,
                bootstrap_lease=bootstrap_lease,
                output_base_guard=output_base_guard,
                output_child=output_child,
                predecessor_identity=predecessor_identity,
                fault_hook=fault_hook,
            )
            current = _bootstrap_output_child(
                current=current,
                session_lease=session_lease,
                profile_lease=profile_lease,
                bootstrap_lease=bootstrap_lease,
                output_base_guard=output_base_guard,
                output_child=output_child,
                predecessor_identity=predecessor_identity,
                fault_hook=fault_hook,
            )
            child = current.output_child_binding
            if not isinstance(child, Mapping):
                raise ValueError("live_start_output_child_binding_missing")
            with hold_plain_directory(
                output_child,
                expected_identity=tuple(child["output_child_identity"]),
            ) as output_guard:
                _emit_pipeline_event("output_deck_identity_lease_enter")
                current = _commit_publication(
                    rendered=validated.rendered,
                    current=current,
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    operation_lease=operation_lease,
                    bootstrap_lease=bootstrap_lease,
                    output_guard=output_guard,
                    operation_evidence=operation_evidence,
                    fault_hook=fault_hook,
                )
                current = _retire_output_child_claim(
                    current=current,
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    bootstrap_lease=bootstrap_lease,
                    output_base_guard=output_base_guard,
                    fault_hook=fault_hook,
                )
                evidence = observe_output_operation_admission_under_lease(
                    operation_lease
                )
                if evidence != operation_evidence:
                    raise ValueError(
                        "live_start_output_operation_binding_changed"
                    )
                _emit_pipeline_event(
                    "output_operation_admission_still_active"
                )
                bootstrap_stack.close()
                _emit_pipeline_event("output_child_bootstrap_lock_exit")
                current = _continue_prepublication_cleanup(
                    current=current,
                    session_lease=session_lease,
                    operation_lease=operation_lease,
                    fault_hook=fault_hook,
                )
                _emit_pipeline_event("output_deck_identity_lease_exit")
            _emit_pipeline_event("output_base_identity_lease_exit")
    finally:
        bootstrap_stack.close()
    revalidate_operator_profile_lease(profile_lease)
    _emit_pipeline_event("profile_lease_still_active")
    observe_output_operation_admission_under_lease(operation_lease)
    _emit_pipeline_event("output_operation_lock_still_active")
    return current


def _drive_live_start_pipeline(
    *,
    run_model: ConfigureRunModel,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_root: Path,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    """Resume the Task-8 prepublication seam before guarded publication."""

    if expected_session.phase is LiveStartPhase.PUBLICATION_COMMITTED:
        return _resume_publication_committed(
            run_model=run_model,
            session_lease=session_lease,
            expected_session=expected_session,
            runtime_root=runtime_root,
            profile_lease=profile_lease,
            operation_lease=operation_lease,
            fault_hook=fault_hook,
        )
    with _lease_validated_prepublication(
        run_model=run_model,
        session_lease=session_lease,
        expected_session=expected_session,
        runtime_root=runtime_root,
        fault_hook=fault_hook,
    ) as validated:
        return _publish_validated_prepublication(
            validated=validated,
            session_lease=session_lease,
            expected_session=validated.updated_session,
            profile_lease=profile_lease,
            operation_lease=operation_lease,
            fault_hook=fault_hook,
        )


def _safe_live_start_deck_name(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or value != value.strip()
        or any(ord(character) < 0x20 for character in value)
    ):
        return None
    return value


class _LiveStartCaptureFailure(RuntimeError):
    """A late acquisition failure with an already validated immutable roster."""

    def __init__(self, deck: FrozenJsonDocument) -> None:
        super().__init__("live_start_input_acquisition_failed")
        self.deck = deck


def _pre_session_result(
    *,
    status: Literal["PROFILE_REQUIRED", "FAILED_PRESERVED"],
    deck_name: str | None,
    error_code: str,
    validated_deck: FrozenJsonDocument | None = None,
) -> LiveStartResult:
    if status not in {"PROFILE_REQUIRED", "FAILED_PRESERVED"}:
        raise ValueError("live_start_pre_session_status_invalid")
    if (
        not isinstance(error_code, str)
        or _session._SAFE_TOKEN.fullmatch(error_code) is None
    ):
        raise ValueError("live_start_pre_session_error_code_invalid")
    safe_name = _safe_live_start_deck_name(deck_name)
    unique = None
    if validated_deck is not None:
        if (
            status != "FAILED_PRESERVED" or safe_name is None
            or not isinstance(validated_deck, FrozenJsonDocument)
        ):
            raise ValueError("live_start_pre_session_roster_invalid")
        deck = validated_deck.to_value()
        if deck["deck_identity"]["deck_name"] != safe_name:
            raise ValueError("live_start_pre_session_roster_name_mismatch")
        unique = len(deck["deck_identity"]["cards"])
        if unique < 1:
            raise ValueError("live_start_pre_session_roster_invalid")
    unsigned = {
        "schema_version": 1,
        "summary_kind": _PRE_SESSION_SUMMARY_KIND,
        "status": status,
        "run_root": None,
        "deck_name": safe_name,
        "candidate_revision": None,
        "unique_main_deck_cards": unique,
        "configured_cards": None,
        "deliberately_unconfigured_cards": None,
        "review_confidence": None,
        "visible_limitations": [],
        "error_code": error_code,
        "retained_safe_state": "NO_SESSION_OR_RUNTIME_WRITE",
    }
    canonical = FrozenJsonDocument.from_value(unsigned).canonical_json
    summary = FrozenJsonDocument.from_value(
        {
            **unsigned,
            "content_sha256": "sha256:" + sha256(canonical).hexdigest(),
        }
    )
    if len(summary.canonical_json) > 16 * 1024:
        raise ValueError("live_start_pre_session_summary_too_large")
    return LiveStartResult(status=status, run_root=None, summary=summary)


def _validate_live_start_request(request: LiveStartRequest) -> None:
    if not isinstance(request, LiveStartRequest):
        raise TypeError("live_start_request_required")
    if _safe_live_start_deck_name(request.deck_name) is None:
        raise ValueError("live_start_deck_name_invalid")
    if (
        not isinstance(request.deck_code, str)
        or not request.deck_code
        or request.deck_code != request.deck_code.strip()
        or len(request.deck_code) > 16 * 1024
    ):
        raise ValueError("live_start_deck_code_invalid")
    if type(request.preview_requested) is not bool:
        raise ValueError("live_start_preview_requested_invalid")
    normalized = request.deck_code + "=" * (-len(request.deck_code) % 4)
    try:
        parsed = parse_deckstring(normalized)
    except Exception as error:
        raise ValueError("live_start_deck_code_invalid") from error
    cards = getattr(parsed, "cards", parsed[0] if isinstance(parsed, tuple) else None)
    heroes = getattr(parsed, "heroes", parsed[1] if isinstance(parsed, tuple) else None)
    if not cards or not heroes or len(heroes) != 1:
        raise ValueError("live_start_deck_code_invalid")


def _policy_profile_value() -> dict[str, Any]:
    policy = load_policy_profile()
    return {
        "policy_id": policy.policy_id,
        "version": policy.version,
        "effective_date": policy.effective_date,
        "content_sha256": policy.content_sha256,
        "rules": json.loads(policy.rules_canonical_json),
    }


def _capture_live_start_inputs(
    request: LiveStartRequest,
    profile: OperatorProfile,
    deck_output_binding: DeckOutputBinding,
) -> FrozenCompilerInputs:
    """Capture every mutable preparation input once, then seal it."""

    cards_payload = load_cards(
        None, deck_name=request.deck_name, deck_code=request.deck_code,
        allow_placeholder=False,
    )
    cards_payload["deck_code"] = request.deck_code
    deck_identity = build_deck_identity(
        deck_name=request.deck_name, deck_code=request.deck_code,
        cards=cards_payload["cards"],
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    deck = FrozenJsonDocument.from_value(
        {"cards_payload": cards_payload, "deck_identity": deck_identity}
    )
    full_cards = FrozenJsonDocument.from_value(
        fetch_latest_cards(timeout=10.0)
    )
    collectible_cards = FrozenJsonDocument.from_value(
        fetch_latest_collectible_cards(timeout=10.0)
    )
    _validate_deck_and_card_closure(
        deck.to_value(), full_cards=full_cards.to_value(),
        collectible_cards=collectible_cards.to_value(),
    )
    bound_date = date.today()
    arguments = argparse.Namespace(
        command="prepare",
        deck_name=request.deck_name,
        deck_code=request.deck_code,
        out=str(deck_output_binding.output_root),
        runtime_root=str(profile.runtime_root),
        guide_sources_json=None,
        source_documents_json=None,
        auto_research_fallback=False,
        json=True,
        cards_json=None,
        claims_json=None,
        plan_reports_dir=None,
        allow_placeholder=False,
        current_date=bound_date.isoformat(),
        collectible_cards_json=None,
        full_cards_json=None,
        skip_semantic_fetch=False,
        source_evidence_json=None,
    )
    try:
        return _capture_live_start_source_inputs(
            request=request, profile=profile, deck_output_binding=deck_output_binding,
            deck=deck, full_cards=full_cards, collectible_cards=collectible_cards,
            bound_date=bound_date, arguments=arguments,
        )
    except (SessionCapabilityError, SessionConflictError, _session.SessionValidationError):
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        raise _LiveStartCaptureFailure(deck) from None


def _capture_live_start_source_inputs(
    *, request: LiveStartRequest, profile: OperatorProfile,
    deck_output_binding: DeckOutputBinding, deck: FrozenJsonDocument,
    full_cards: FrozenJsonDocument, collectible_cards: FrozenJsonDocument,
    bound_date: date, arguments: argparse.Namespace,
) -> FrozenCompilerInputs:
    preconfig = build_preconfig_context(
        arguments,
        current_date=bound_date,
        source_authority_consumer="prepare",
        load_cards_fn=lambda *_args, **_kwargs: deck.to_value()["cards_payload"],
        fetch_latest_cards_fn=lambda timeout=10.0: deepcopy(
            full_cards.to_value()
        ),
        fetch_latest_collectible_cards_fn=lambda timeout=10.0: deepcopy(
            collectible_cards.to_value()
        ),
    )
    baseline_receipt = load_globalvalues_baseline(profile.runtime_root)
    baseline = normalize_globalvalues_decision_baseline(
        baseline_receipt["baseline"]
    )
    preconfig = {
        **preconfig,
        "cards_payload": {**preconfig["cards_payload"], "deck_code": request.deck_code},
        "policy_profile": _policy_profile_value(),
        "globalvalues_baseline": baseline,
        "globalvalues_baseline_receipt": baseline_receipt,
    }
    snapshot = PackageResolutionSnapshot.from_preconfig(preconfig)
    return freeze_compiler_inputs(
        snapshot=snapshot,
        deck={
            "cards_payload": preconfig["cards_payload"],
            "deck_identity": preconfig["deck_identity"],
        },
        full_cards=full_cards,
        collectible_cards=collectible_cards,
        source_acquisition={
            "guide_builder_receipt": preconfig["guide_builder_receipt"],
            "source_evidence_report": preconfig["source_evidence_report"],
        },
        source_documents={
            "guide_sources": preconfig["guide_sources_generated"]
        },
        globalvalues_baseline=baseline,
        bound_date=bound_date.isoformat(),
        runtime_grammar_version=_RUNTIME_GRAMMAR_VERSION,
        compiler_contract_id=_COMPILER_CONTRACT_ID,
        operator_profile=profile,
        deck_output_binding=deck_output_binding,
    )


def _require_or_create_plain_child(parent: Path, name: str) -> Path:
    child = parent / name
    parent_identity = path_identity(parent)
    try:
        status = child.lstat()
    except FileNotFoundError:
        identity = secure_create_directory(
            child,
            expected_parent_identity=parent_identity,
        )
        status = child.lstat()
        if path_identity_from_status(status) != identity:
            raise SessionConflictError("live_start_context_directory_changed")
    if (
        not stat.S_ISDIR(status.st_mode)
        or status_is_reparse(status)
        or path_identity(parent) != parent_identity
    ):
        raise SessionConflictError("live_start_context_directory_invalid")
    require_plain_directory(child)
    return child


def _materialize_starter_context(
    *,
    local_app_data_root: Path,
    run_id: str,
    payload: bytes,
) -> Path:
    state_root = local_app_data_root / "HSConfig"
    require_plain_directory(state_root)
    contexts_root = _require_or_create_plain_child(state_root, "contexts")
    context_root = _require_or_create_plain_child(contexts_root, run_id)
    path = context_root / "starter_context.json"
    if path_lexists(path):
        if _read_plain_bytes(path, maximum_size=STARTER_CONTEXT_MAX_BYTES) != payload:
            raise SessionConflictError("live_start_external_context_changed")
        return path
    atomic_write_reserved_bytes(
        path=path,
        payload=payload,
        expected_parent_identity=path_identity(context_root),
        expected_predecessor_identity=None,
        expected_predecessor_sha256=None,
        maximum_size=2 * 1024 * 1024,
    )
    return path


_RESEARCH_VISIBLE_MESSAGES = {
    "discovery_unavailable": "Guide discovery was unavailable.",
    "discovery_budget_exhausted": "The guide search budget was exhausted.",
    "no_useful_observations": "No useful card-specific guide observations were retained.",
    "no_verified_exact_guide_observations": "No retained observation has verified exact-deck guide identity.",
    "acquisition_research_budget_exhausted": "The shared page-acquisition deadline was exhausted.",
    "source_context_incomplete": "Some selected guide excerpts omit adjacent context; review the limitation before relying on them.",
    "acquisition_failed": "A guide page could not be acquired.",
    "acquisition_interrupted": "A guide page acquisition was interrupted.",
    "acquisition_started": "A guide page acquisition has no completed result.",
    "acquisition_source_body_too_large": "A guide page exceeded the permitted acquisition size.",
    "acquisition_TimeoutError": "A guide page request timed out.",
}
_UNKNOWN_RESEARCH_LIMITATION = "Additional research limitations are present in the preserved evidence."
_LIMITED_REVIEW_MESSAGE = "Independent reviewer confidence is limited."


def _visible_research_limitations(
    codes: object, *, review: ValidatedStarterReview | None = None
) -> tuple[str, ...]:
    if not isinstance(codes, (list, tuple)):
        raise SessionConflictError("live_start_quality_limitations_invalid")
    messages = set()
    for code in codes:
        if not isinstance(code, str):
            raise SessionConflictError("live_start_quality_limitations_invalid")
        if code in _RESEARCH_VISIBLE_MESSAGES:
            messages.add(_RESEARCH_VISIBLE_MESSAGES[code])
        elif re.fullmatch(r"acquisition_http_status_[1-5][0-9]{2}", code):
            messages.add("A guide page returned an unsuccessful HTTP response.")
        else:
            messages.add(_UNKNOWN_RESEARCH_LIMITATION)
    if review is not None and review.confidence == "limited":
        messages.add(_LIMITED_REVIEW_MESSAGE)
        messages.add("See the preserved review rationale bound to " + review.document.content_sha256 + ".")
    result = tuple(sorted(messages))
    if len(result) > 32 or any(
        not message or len(message) > 256 or any(ord(c) < 32 for c in message)
        for message in result
    ):
        raise SessionConflictError("live_start_quality_limitations_invalid")
    return result


def _starter_context_limitations(
    context_value: Mapping[str, Any], *, review: ValidatedStarterReview | None = None
) -> tuple[str, ...]:
    source_evidence = context_value.get("source_evidence")
    if context_value.get("schema_version") == 3:
        research = context_value.get("research_evidence")
        receipt = source_evidence.get("guide_builder_receipt") if isinstance(source_evidence, Mapping) else None
        depth = receipt.get("source_depth_status") if isinstance(receipt, Mapping) else None
        if (not isinstance(research, Mapping) or "limitations" not in research
            or not isinstance(depth, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]+", depth)):
            raise SessionConflictError("live_start_quality_limitations_invalid")
        messages = set(_visible_research_limitations(research["limitations"], review=review))
        if depth != "source_backed":
            messages.add("Guide depth is limited; static card semantics remain visible.")
        return tuple(sorted(messages))
    summary = (
        source_evidence.get("guide_sources_summary")
        if isinstance(source_evidence, Mapping)
        else None
    )
    source_depth = (
        summary.get("source_depth_status")
        if isinstance(summary, Mapping)
        else None
    )
    if source_depth == "source_backed":
        return ()
    return ("Guide depth is limited; static card semantics remain visible.",)


def _read_plain_bytes(path: Path, *, maximum_size: int) -> bytes:
    status = plain_file_status(path)
    raw = read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=maximum_size,
    )
    if len(raw) != status.st_size:
        raise SessionConflictError("live_start_external_document_changed")
    return raw


def _write_external_authority_source(
    *,
    session_root: Path,
    name: str,
    payload: bytes,
) -> Path:
    state_root = session_root.parent.parent
    contexts_root = _require_or_create_plain_child(state_root, "contexts")
    context_root = _require_or_create_plain_child(
        contexts_root,
        session_root.name,
    )
    path = context_root / name
    if path_lexists(path):
        if _read_plain_bytes(path, maximum_size=max(1, len(payload))) != payload:
            raise SessionConflictError("live_start_external_authority_changed")
        return path
    atomic_write_reserved_bytes(
        path=path,
        payload=payload,
        expected_parent_identity=path_identity(context_root),
        expected_predecessor_identity=None,
        expected_predecessor_sha256=None,
        maximum_size=max(1, len(payload)),
    )
    return path


def _load_unsigned_draft(path: Path, *, maximum_size: int) -> dict[str, Any]:
    raw = _read_plain_bytes(Path(path), maximum_size=maximum_size)
    document = FrozenJsonDocument.from_json_bytes(raw)
    value = document.to_value()
    if not isinstance(value, dict):
        raise ValueError("live_start_draft_not_object")
    return value


def _ensure_session_artifact_parent(
    *,
    session_root: Path,
    logical_path: str,
) -> Path:
    parts = logical_path.split("/")
    if len(parts) != 2 or parts[0] not in {"starter", "receipts"}:
        raise SessionConflictError("live_start_document_path_invalid")
    return _require_or_create_plain_child(session_root, parts[0])


def _materialize_pending_document(
    *,
    session_root: Path,
    current: LiveStartSession,
    row: Mapping[str, Any],
) -> None:
    actions = _session._require_starter_document_pending_rows(current, root=session_root)
    pending = current.pending_transition
    if (
        not actions or pending["stage"] != "PRIMARY_APPLIED"
        or pending["next_action_index"] >= len(actions)
        or actions[pending["next_action_index"]] != row
    ):
        raise SessionConflictError("live_start_document_action_invalid")
    logical_path = str(row["logical_path"])
    target = session_root / logical_path
    source = Path(str(row["source_path"]))
    require_plain_directory(source.parent)
    source_status = plain_file_status(source)
    if (
        path_identity_from_status(source_status) != tuple(row["source_identity"])
        or path_identity(source.parent) != tuple(row["source_parent_identity"])
    ):
        raise SessionConflictError("live_start_pending_source_changed")
    expected_size = int(row["size"])
    expected_sha256 = str(row["sha256"])
    payload = read_file_no_follow(
        source, expected_status=source_status, maximum_size=max(1, expected_size)
    )
    if len(payload) != expected_size or _sha256_bytes(payload) != expected_sha256:
        raise SessionConflictError("live_start_pending_source_changed")
    parent = _ensure_session_artifact_parent(
        session_root=session_root,
        logical_path=logical_path,
    )
    parent_identity = path_identity(parent)
    reserved = target.with_name(f".{target.name}.live-start-atomic.tmp")
    if path_lexists(reserved):
        reserved_status = plain_file_status(reserved)
        if reserved_status.st_size > 2 * 1024 * 1024:
            raise SessionConflictError("live_start_document_reserved_temp_size_invalid")
        secure_unlink(
            reserved, expected_identity=path_identity_from_status(reserved_status),
            expected_parent_identity=parent_identity, missing_ok=False,
        )
    def recheck_source() -> None:
        require_plain_directory(source.parent)
        if (
            path_identity(source.parent) != tuple(row["source_parent_identity"])
            or path_identity(source) != tuple(row["source_identity"])
            or read_file_no_follow(
                source, expected_status=source_status, maximum_size=max(1, expected_size)
            ) != payload
        ):
            raise SessionConflictError("live_start_pending_source_changed")

    write_maximum_size = max(1, expected_size)
    if path_lexists(target):
        status = plain_file_status(target)
        if status.st_size > 2 * 1024 * 1024:
            raise SessionConflictError("live_start_pending_target_size_invalid")
        write_maximum_size = max(write_maximum_size, status.st_size)
        existing = read_file_no_follow(
            target,
            expected_status=status,
            maximum_size=write_maximum_size,
        )
        existing_sha256 = _sha256_bytes(existing)
        if existing_sha256 == expected_sha256 and existing == payload:
            recheck_source()
            return
        predecessor_sha256 = current.artifact_bindings.get(logical_path)
        if predecessor_sha256 != existing_sha256:
            raise SessionConflictError("live_start_pending_target_changed")
        predecessor_identity = path_identity_from_status(status)
    else:
        if logical_path in current.artifact_bindings:
            raise SessionConflictError("live_start_pending_predecessor_missing")
        predecessor_identity = None
        predecessor_sha256 = None
    recheck_source()
    atomic_write_reserved_bytes(
        path=target,
        payload=payload,
        expected_parent_identity=parent_identity,
        expected_predecessor_identity=predecessor_identity,
        expected_predecessor_sha256=predecessor_sha256,
        maximum_size=write_maximum_size,
    )


def _retire_pending_document(
    *,
    session_root: Path,
    row: Mapping[str, Any],
    successor_bindings: Mapping[str, Any],
) -> None:
    logical_path = str(row["logical_path"])
    target = session_root / logical_path
    if path_lexists(target):
        status = plain_file_status(target)
        parent_identity = path_identity(target.parent)
        raw = read_file_no_follow(
            target, expected_status=status, maximum_size=int(row["size"])
        )
        if len(raw) != row["size"] or _sha256_bytes(raw) != row["sha256"]:
            raise SessionConflictError("live_start_retired_document_changed")
        secure_unlink(
            target,
            expected_identity=path_identity_from_status(status),
            expected_parent_identity=parent_identity,
            missing_ok=False,
        )
    if not path_lexists(target.parent):
        return
    parent_identity = path_identity(target.parent)
    if not any(
        logical.startswith(f"{target.parent.name}/")
        for logical in successor_bindings
    ):
        try:
            next(target.parent.iterdir())
        except StopIteration:
            secure_rmdir_verified(
                target.parent,
                expected_identity=parent_identity,
                expected_parent_identity=path_identity(session_root),
            )


def _continue_pending_document_install(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    final_event: str,
) -> LiveStartSession:
    pending = current.pending_transition
    if not isinstance(pending, Mapping):
        raise SessionConflictError("live_start_document_pending_missing")
    _session._require_session_lease(session_lease)
    if not _session._require_starter_document_pending_rows(
        current, root=session_lease.session_root
    ):
        raise SessionConflictError("live_start_document_actions_invalid")
    if pending["stage"] == "PREPARED":
        pending_value = _session._thaw(pending)
        pending_value.pop("content_sha256", None)
        pending_value["stage"] = "PRIMARY_APPLIED"
        current = _session._transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=current,
            event="same_phase_cas",
            changes={
                "pending_transition": _session._seal_pending(pending_value)
            },
        )
        pending = current.pending_transition
        if not isinstance(pending, Mapping):
            raise SessionConflictError("live_start_document_pending_missing")
    if pending["stage"] != "PRIMARY_APPLIED":
        raise SessionConflictError("live_start_document_pending_stage_invalid")
    actions = pending["actions"]
    if not _session._starter_document_pending_rows(current):
        raise SessionConflictError("live_start_document_actions_invalid")
    _session._validate_starter_document_postconditions(
        session_lease=session_lease, session=current
    )
    action_index = int(pending["next_action_index"])
    while action_index < len(actions):
        row = actions[action_index]
        if not isinstance(row, Mapping):
            raise SessionConflictError("live_start_document_action_invalid")
        if row.get("action") == "install":
            _materialize_pending_document(
                session_root=session_lease.session_root,
                current=current,
                row=row,
            )
        elif row.get("action") == "retire":
            _retire_pending_document(
                session_root=session_lease.session_root,
                row=row,
                successor_bindings=pending["successor_artifact_bindings"],
            )
        else:
            raise SessionConflictError("live_start_document_action_invalid")
        pending_value = _session._thaw(pending)
        pending_value.pop("content_sha256", None)
        action_index += 1
        pending_value["next_action_index"] = action_index
        current = _session._transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=current,
            event="same_phase_cas",
            changes={
                "pending_transition": _session._seal_pending(pending_value)
            },
        )
        pending = current.pending_transition
        if not isinstance(pending, Mapping):
            raise SessionConflictError("live_start_document_pending_missing")
    _session._validate_starter_document_postconditions(
        session_lease=session_lease, session=current, complete=True
    )
    return _session._transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=current,
        event=final_event,
        changes={
            "artifact_bindings": pending["successor_artifact_bindings"],
            "pending_transition": None,
        },
    )


def _install_session_documents(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    operation: str,
    final_event: str,
    documents: Mapping[str, bytes],
) -> LiveStartSession:
    successor_bindings = dict(current.artifact_bindings)
    retire_rows: list[dict[str, Any]] = []
    if final_event == "replacement_draft":
        for logical_path in _session._DOWNSTREAM_REVISION_ARTIFACTS:
            digest = successor_bindings.pop(logical_path, None)
            path = session_lease.session_root / logical_path
            if digest is not None and path_lexists(path):
                raw = _read_plain_bytes(path, maximum_size=64 * 1024 * 1024)
                retire_rows.append(
                    {
                        "action": "retire",
                        "logical_path": logical_path,
                        "size": len(raw),
                        "sha256": digest,
                    }
                )
    install_rows: list[dict[str, Any]] = []
    for index, (logical_path, payload) in enumerate(sorted(documents.items())):
        digest = _sha256_bytes(payload)
        source_path = _write_external_authority_source(
            session_root=session_lease.session_root,
            name=(
                f"{operation}-r{current.candidate_revision}-"
                f"u{current.revisions_used}-{index}-{Path(logical_path).name}"
            ),
            payload=payload,
        )
        successor_bindings[logical_path] = digest
        install_rows.append(
            {
                "action": "install",
                "logical_path": logical_path,
                "source_path": str(source_path),
                "source_identity": list(path_identity(source_path)),
                "source_parent_identity": list(path_identity(source_path.parent)),
                "size": len(payload),
                "sha256": digest,
            }
        )
    pending = _session._empty_pending_transition(
        session=current,
        operation=operation,
        external_file_action=None,
    )
    target_phase = {
        "initial_draft": LiveStartPhase.CANDIDATE_DRAFTED,
        "replacement_draft": LiveStartPhase.CANDIDATE_DRAFTED,
        "candidate_valid": LiveStartPhase.CANDIDATE_VALIDATED,
        "review_approved": LiveStartPhase.REVIEW_APPROVED,
    }[final_event]
    pending.update(
        {
            "target_phase": target_phase.value,
            "target_candidate_revision": (
                current.candidate_revision + 1
                if final_event == "replacement_draft"
                else current.candidate_revision
            ),
            "successor_artifact_bindings": successor_bindings,
            "actions": [*install_rows, *retire_rows],
        }
    )
    prepared = _session._transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=current,
        event="same_phase_cas",
        changes={"pending_transition": _session._seal_pending(pending)},
    )
    return _continue_pending_document_install(
        session_lease=session_lease,
        current=prepared,
        final_event=final_event,
    )


def _load_bound_starter_context(
    *,
    session_root: Path,
) -> StarterContext:
    version = _persisted_live_document_version(session_root)
    document = load_starter_document(
        session_root / "starter/starter_context.json",
        maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
        expected_fields=QUALITY_STARTER_CONTEXT_FIELDS
        if version == 3
        else SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
        schema_version=version,
    )
    return validate_starter_context_document(document)


def _load_bound_candidate(
    *,
    session_root: Path,
    context: StarterContext,
) -> ValidatedStarterCandidate:
    version = context.document.to_value()["schema_version"]
    document = load_starter_document(
        session_root / "starter/starter_config_candidate.json",
        maximum_bytes=STARTER_CANDIDATE_MAX_BYTES,
        expected_fields=QUALITY_STARTER_CANDIDATE_FIELDS
        if version == 3
        else SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
        schema_version=version,
    )
    return validate_starter_candidate(document, context=context)


def _persisted_live_document_version(root: Path) -> int:
    from hsconfig.input_snapshot_manifest import (
        validate_input_snapshot_manifest_document,
    )

    raw = _read_plain_bytes(
        root / "session.json", maximum_size=_session.LIVE_START_SESSION_MAX_BYTES
    )
    current = _session._load_session_bytes(raw, session_identity=None)
    manifest_raw = _read_plain_bytes(
        root / "inputs/input_snapshot_manifest.json", maximum_size=256 * 1024
    )
    if _sha256_bytes(manifest_raw) != current.artifact_bindings.get(
        "inputs/input_snapshot_manifest.json"
    ):
        raise SessionConflictError("live_start_manifest_physical_binding_changed")
    manifest = validate_input_snapshot_manifest_document(
        FrozenJsonDocument.from_json_bytes(manifest_raw)
    )
    version = 3 if current.schema_version == 2 else 2
    live_contract_for_versions(
        session=current.schema_version,
        manifest=manifest.document.to_value()["schema_version"],
        context=version,
        candidate=version,
        review=version,
        compiler=manifest.compiler_inputs.to_value()["compiler_contract_id"],
    )
    if manifest.document.content_sha256 != current.input_snapshot_manifest_sha256:
        raise SessionConflictError("live_start_manifest_binding_changed")
    return version


def _load_quality_candidate_receipt(
    *, root: Path, current: LiveStartSession | None = None
):
    if current is None:
        current = _session._load_session_bytes(
            _read_plain_bytes(
                root / "session.json",
                maximum_size=_session.LIVE_START_SESSION_MAX_BYTES,
            ),
            session_identity=None,
        )
    if current.schema_version != 2:
        return None
    logical = "receipts/candidate_validation.json"
    raw = _read_plain_bytes(root / logical, maximum_size=512 * 1024)
    if _sha256_bytes(raw) != current.artifact_bindings.get(logical):
        raise SessionConflictError(
            "live_start_quality_receipt_physical_binding_changed"
        )
    document = FrozenJsonDocument.from_json_bytes(raw)
    _session.validate_validation_receipt(
        receipt_kind="candidate_validation",
        value=document.to_value(),
        run_id=current.run_id,
        candidate_revision=current.candidate_revision,
    )
    return document


def _load_bound_revision_review(
    *, session_root: Path, current: LiveStartSession, context: StarterContext,
) -> ValidatedStarterReview:
    logical_path = "starter/starter_config_review.json"
    raw = _read_plain_bytes(
        session_root / logical_path, maximum_size=STARTER_REVIEW_MAX_BYTES + 1,
    )
    if _sha256_bytes(raw) != current.artifact_bindings[logical_path]:
        raise SessionConflictError("live_start_revision_review_bytes_changed")
    # Requested reviews retain Session-canonical bytes (including one LF).
    # Preserve their claimed self-digest; validation must never repair it.
    value = _session._decode_canonical_json(raw)
    document = StarterDocument(
        document=FrozenJsonDocument.from_value(value),
        content_sha256=value.get("content_sha256"),
    )
    candidate = _load_bound_candidate(session_root=session_root, context=context)
    receipt = None
    if current.schema_version == 2:
        if (
            current.phase is not LiveStartPhase.CANDIDATE_DRAFTED
            or current.pending_transition is not None
            or current.terminal_status is not None
            or current.revisions_used != current.candidate_revision
            or value.get("review_status") != "revision_requested"
        ):
            raise SessionConflictError(
                "live_start_quality_revision_receipt_cursor_invalid"
            )
        source_root = session_root.parent.parent / "contexts" / current.run_id
        source = source_root / (
            f"install_candidate_validation-r{current.candidate_revision}-"
            f"u{current.candidate_revision - 1}-0-candidate_validation.json"
        )
        with hold_plain_directory(source_root.parent) as contexts_guard:
            with hold_plain_directory(source_root) as source_guard:
                raw_receipt = _read_plain_bytes(source, maximum_size=256 * 1024)
                contexts_guard.validate()
                source_guard.validate()
        receipt = FrozenJsonDocument.from_value(
            _session._decode_canonical_json(raw_receipt)
        )
        _session.validate_validation_receipt(
            receipt_kind="candidate_validation",
            value=receipt.to_value(),
            run_id=current.run_id,
            candidate_revision=current.candidate_revision,
        )
    review = validate_starter_review(
        document, context=context, candidate=candidate, validation_receipt=receipt
    )
    if (review.review_status != "revision_requested"
        or review.candidate_revision != current.candidate_revision):
        raise SessionConflictError("live_start_revision_review_cursor_invalid")
    return review


def _review_revision_diagnostic(
    *, current: LiveStartSession, review: ValidatedStarterReview,
) -> FrozenJsonDocument:
    requests = [row.to_value() for row in review.revision_requests]
    return _sealed_diagnostic({
        "schema_version": 1,
        "diagnostic_kind": "live_start_review_validation",
        "status": "revision_required",
        "candidate_revision": current.candidate_revision,
        "next_candidate_revision": current.candidate_revision + 1,
        "revisions_used": current.revisions_used,
        "findings": [row["code"] for row in requests],
        "revision_requests": requests,
    })


def _candidate_counts(
    *,
    context: StarterContext | None,
    candidate: ValidatedStarterCandidate | None,
    frozen: FrozenCompilerInputs | None = None,
) -> tuple[int, int | None, int | None]:
    if context is None:
        if candidate is not None or frozen is None:
            raise SessionConflictError("live_start_failure_count_authority_missing")
        return len(frozen.deck.to_value()["deck_identity"]["cards"]), None, None
    cards = context.document.to_value()["cards"]
    unique_cards = len(cards)
    if candidate is None:
        return unique_cards, None, None
    dispositions = candidate.document.to_value()["card_dispositions"]
    configured = sum(
        row["disposition"] == "configured" for row in dispositions
    )
    return unique_cards, configured, unique_cards - configured


def _failure_result_intent(
    *,
    current: LiveStartSession,
    context: StarterContext | None,
    candidate: ValidatedStarterCandidate | None,
    error_code: str,
    frozen: FrozenCompilerInputs | None = None,
    incoming_review: ValidatedStarterReview | None = None,
) -> Mapping[str, Any]:
    if isinstance(getattr(current, "result_intent", None), Mapping):
        return current.result_intent
    unique, configured, unconfigured = _candidate_counts(
        context=context,
        candidate=candidate,
        frozen=frozen,
    )
    publication = current.publication_binding
    if isinstance(publication, Mapping):
        publication_revision = publication["revision"]
        publication_sha256 = publication["content_root_sha256"]
        retained_safe_state = "PUBLICATION_RETAINED_RUNTIME_UNCHANGED"
    else:
        publication_revision = None
        publication_sha256 = None
        retained_safe_state = "NO_PUBLICATION_OR_RUNTIME_WRITE"
    limitations = _starter_context_limitations(context.document.to_value()) if context is not None else ()
    confidence = None
    if current.schema_version == 2:
        if context is None:
            if (frozen is None or frozen.quality_inputs is None
                or frozen.manifest.document.content_sha256 != current.input_snapshot_manifest_sha256):
                raise SessionConflictError("live_start_quality_failure_input_missing")
            quality = frozen.quality_inputs.to_value()
            if quality["research_request_sha256"] != current.research_binding["request_sha256"]:
                raise SessionConflictError("live_start_quality_failure_input_changed")
            limitations = _visible_research_limitations(quality["research_result"]["limitations"])
        if incoming_review is not None:
            if (context is None or candidate is None
                or incoming_review.starter_context_sha256 != context.document.content_sha256
                or incoming_review.candidate_sha256 != candidate.document.content_sha256
                or incoming_review.candidate_revision != candidate.candidate_revision
                or candidate.candidate_revision != current.candidate_revision):
                raise SessionConflictError("live_start_quality_failure_review_changed")
            confidence = incoming_review.confidence
            if confidence == "limited":
                # Incoming exhausted-budget feedback was validated, not installed.
                limitations = tuple(sorted({*limitations, _LIMITED_REVIEW_MESSAGE}))
    return _session.seal_embedded_document(
        "result_intent",
        {
            "schema_version": 1,
            "intent_kind": _session.LIVE_START_RESULT_INTENT_KIND,
            "run_id": current.run_id,
            "terminal_status": "FAILED_PRESERVED",
            "deck_name": current.deck_name,
            "candidate_revision": current.candidate_revision,
            "unique_main_deck_cards": unique,
            "configured_cards": configured,
            "deliberately_unconfigured_cards": unconfigured,
            "review_confidence": confidence,
            "visible_limitations": list(limitations),
            "apply_attempt_id": None,
            "publication_revision": publication_revision,
            "publication_content_root_sha256": publication_sha256,
            "raw_apply_status": None,
            "physical_disposition": None,
            "runtime_match_status": "not_run",
            "runtime_match_sha256": None,
            "package_root_sha256": None,
            "last_apply_receipt_sha256": None,
            "runtime_state_sha256": None,
            "deck_config_ini_sha256": None,
            "retained_attempt_record_path": None,
            "retained_attempt_record_identity": None,
            "retained_attempt_record_sha256": None,
            "retained_journal_path": None,
            "retained_journal_identity": None,
            "retained_journal_sha256": None,
            "retained_target_owner_journal_path": None,
            "retained_target_owner_journal_identity": None,
            "retained_target_owner_journal_sha256": None,
            "retained_candidate_identity": None,
            "runtime_admission_path": None,
            "runtime_admission_parent_identity": None,
            "runtime_admission_identity": None,
            "runtime_admission_sha256": None,
            "error_code": error_code,
            "retained_safe_state": retained_safe_state,
        },
    )


def _load_terminal_result(
    *,
    session_root: Path,
    terminal: LiveStartSession,
) -> LiveStartResult:
    if terminal.terminal_status is None:
        raise SessionConflictError("live_start_terminal_result_missing")
    raw = _read_plain_bytes(
        session_root / "result/summary.json",
        maximum_size=_session.LIVE_START_RESULT_SUMMARY_MAX_BYTES,
    )
    summary = FrozenJsonDocument.from_json_bytes(raw)
    return LiveStartResult(
        status=terminal.terminal_status,  # type: ignore[arg-type]
        run_root=session_root,
        summary=summary,
    )


def _terminalize_preapply_failure_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    context: StarterContext | None,
    candidate: ValidatedStarterCandidate | None,
    error_code: str,
    incoming_review: ValidatedStarterReview | None = None,
) -> LiveStartResult:
    frozen = None
    if context is None:
        if candidate is not None:
            raise SessionConflictError("live_start_failure_count_authority_missing")
        current_on_disk = _session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        if current_on_disk != current:
            raise SessionConflictError("live_start_failure_session_changed")
        frozen = load_frozen_compiler_inputs(session_lease.session_root)
    intent = _failure_result_intent(
        current=current,
        context=context,
        candidate=candidate,
        error_code=error_code,
        frozen=frozen,
        incoming_review=incoming_review,
    )
    intent_cursor = _session._transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=current,
        event="same_phase_cas",
        changes={"result_intent": intent},
    )
    terminal = _session.complete_live_start_under_lock(
        session_lease=session_lease,
        expected_result_session=intent_cursor,
    )
    return _load_terminal_result(
        session_root=session_lease.session_root,
        terminal=terminal,
    )


def _sealed_diagnostic(value: Mapping[str, Any]) -> FrozenJsonDocument:
    unsigned = dict(value)
    canonical = FrozenJsonDocument.from_value(unsigned).canonical_json
    return FrozenJsonDocument.from_value(
        {
            **unsigned,
            "content_sha256": "sha256:" + sha256(canonical).hexdigest(),
        }
    )


@dataclass(frozen=True, slots=True)
class LiveStartDiscovery:
    run_root: Path
    acquisition_request_path: Path
    acquisition_request_sha256: str


_QUALITY_RESEARCH_QUERY_LIMIT = 2
_QUALITY_RESEARCH_URL_LIMIT = 3
_QUALITY_REVISION_LIMIT = 2


def _quality_summary_progress(
    *, run_root: Path, current: LiveStartSession
) -> Mapping[str, Any]:
    from hsconfig.live_start_research import (
        validate_research_attempts,
        validate_research_draft,
    )

    logical = "research/progress.json"
    raw = _read_plain_bytes(
        run_root / logical,
        maximum_size=_session.QUALITY_FILE_LIMITS[logical],
    )
    if _sha256_bytes(raw) != current.artifact_bindings.get(logical):
        raise SessionConflictError("live_start_quality_progress_binding_changed")
    document = FrozenJsonDocument.from_json_bytes(raw)
    if document.canonical_json != raw:
        raise SessionConflictError("live_start_quality_progress_noncanonical")
    progress = document.to_value()
    expected = {
        "schema_version",
        "request_sha256",
        "search_slots",
        "draft",
        "deadline_utc",
        "attempts",
        "source_records",
        "source_acquisition_reports",
    }
    slots = progress.get("search_slots") if isinstance(progress, dict) else None
    if (
        not isinstance(progress, dict)
        or set(progress) != expected
        or progress.get("schema_version") != 1
        or progress.get("request_sha256")
        != current.research_binding["request_sha256"]
        or not isinstance(slots, list)
        or len(slots) > _QUALITY_RESEARCH_QUERY_LIMIT
        or any(
            not isinstance(row, dict)
            or set(row) != {"query", "state"}
            or not isinstance(row["query"], str)
            or not row["query"]
            or row["state"] != "reserved_unknown"
            for row in slots
        )
    ):
        raise SessionConflictError("live_start_quality_progress_invalid")
    draft = progress["draft"]
    urls: list[Any] = (
        draft.get("urls", []) if isinstance(draft, dict) else []
    )
    if (
        (draft is not None and not isinstance(draft, dict))
        or not isinstance(urls, list)
        or len(urls) > _QUALITY_RESEARCH_URL_LIMIT
        or any(not isinstance(url, str) or not url for url in urls)
    ):
        raise SessionConflictError("live_start_quality_progress_invalid")
    if draft is None:
        if (
            progress["deadline_utc"] is not None
            or progress["attempts"]
            or progress["source_records"]
            or progress["source_acquisition_reports"]
        ):
            raise SessionConflictError("live_start_quality_progress_invalid")
    else:
        admitted_urls, _outcome = validate_research_draft(
            draft,
            request_sha256=current.research_binding["request_sha256"],
        )
        if any(
            attempt.get("url") not in admitted_urls
            for attempt in progress["attempts"]
            if isinstance(attempt, Mapping)
        ):
            raise SessionConflictError("live_start_quality_progress_invalid")
        validate_research_attempts(
            acquired={"source_records": progress["source_records"]},
            discovery_outcome=draft["discovery_outcome"],
            attempts=progress["attempts"],
            deadline_utc=progress["deadline_utc"],
        )
    return progress


def _read_quality_bound_document(
    *, run_root: Path, current: LiveStartSession, logical: str, maximum_size: int
) -> FrozenJsonDocument | None:
    expected = current.artifact_bindings.get(logical)
    if expected is None:
        return None
    raw = _read_plain_bytes(run_root / logical, maximum_size=maximum_size)
    if _sha256_bytes(raw) != expected:
        raise SessionConflictError("live_start_quality_input_changed")
    document = FrozenJsonDocument.from_json_bytes(raw)
    if document.canonical_json != raw:
        raise SessionConflictError("live_start_quality_input_noncanonical")
    return document


def _quality_starter_document(document: FrozenJsonDocument) -> StarterDocument:
    value = document.to_value()
    if not isinstance(value, dict):
        raise SessionConflictError("live_start_quality_starter_document_invalid")
    return StarterDocument(document=document, content_sha256=value.get("content_sha256"))


def _quality_bound_review(
    *, run_root: Path, current: LiveStartSession, context: StarterContext
) -> ValidatedStarterReview | None:
    review_logical = "starter/starter_config_review.json"
    if review_logical not in current.artifact_bindings:
        return None
    # Feedback is Session-canonical (with LF), unlike installed approvals.
    # Inspect only captured-bound bytes; never re-open the session or old receipt.
    feedback_phase = current.phase in {
        LiveStartPhase.CANDIDATE_DRAFTED, LiveStartPhase.CANDIDATE_VALIDATED
    } and current.revisions_used > 0
    if feedback_phase:
        raw = _read_plain_bytes(run_root / review_logical, maximum_size=STARTER_REVIEW_MAX_BYTES + 1)
        if _sha256_bytes(raw) != current.artifact_bindings[review_logical]:
            raise SessionConflictError("live_start_quality_input_changed")
        if raw.endswith(b"\n"):
            value = _session._decode_canonical_json(raw)
            document = _quality_starter_document(FrozenJsonDocument.from_value(value))
            unsigned = dict(value)
            unsigned.pop("content_sha256", None)
            revision = value.get("candidate_revision")
            if (set(value) != QUALITY_STARTER_REVIEW_FIELDS
                or type(value.get("schema_version")) is not int or value["schema_version"] != 3
                or document.content_sha256 != _sha256_bytes(FrozenJsonDocument.from_value(unsigned).canonical_json)
                or value.get("review_status") != "revision_requested"
                or type(revision) is not int or not 1 <= revision <= current.revisions_used
                or revision > current.candidate_revision
                or (revision == current.candidate_revision and current.phase is not LiveStartPhase.CANDIDATE_DRAFTED)):
                raise SessionConflictError("live_start_quality_review_binding_invalid")
            return None
    review_doc = _read_quality_bound_document(
        run_root=run_root, current=current, logical=review_logical,
        maximum_size=STARTER_REVIEW_MAX_BYTES,
    )
    candidate_doc = _read_quality_bound_document(
        run_root=run_root, current=current, logical="starter/starter_config_candidate.json",
        maximum_size=STARTER_CANDIDATE_MAX_BYTES,
    )
    if candidate_doc is None or "receipts/candidate_validation.json" not in current.artifact_bindings:
        return None
    candidate = validate_starter_candidate(_quality_starter_document(candidate_doc), context=context)
    if candidate.candidate_revision != current.candidate_revision:
        raise SessionConflictError("live_start_quality_candidate_revision_changed")
    receipt = _load_quality_candidate_receipt(root=run_root, current=current)
    review = validate_starter_review(
        _quality_starter_document(review_doc), context=context, candidate=candidate,
        validation_receipt=receipt,
    )
    if review.review_status != "approved":
        raise SessionConflictError("live_start_quality_review_binding_invalid")
    return review


def _quality_available_limitations(
    *, run_root: Path, current: LiveStartSession, progress: Mapping[str, Any]
) -> tuple[str, ...]:
    from hsconfig.input_snapshot_manifest import (
        QUALITY_INPUT_FIELDS, validate_input_snapshot_manifest_document, validate_research_result,
    )

    if isinstance(current.result_intent, Mapping):
        return tuple(current.result_intent["visible_limitations"])
    if current.phase is LiveStartPhase.DISCOVERY_REQUIRED:
        codes = []
        draft = progress["draft"]
        if draft is not None and draft["discovery_outcome"] != "completed":
            codes.append("discovery_" + draft["discovery_outcome"])
        codes.extend("acquisition_" + str(row["error"] or row["state"])
                     for row in progress["attempts"] if row["state"] != "completed")
        return tuple(sorted({"Guide research is not complete.", *_visible_research_limitations(codes)}))
    manifest_logical = "inputs/input_snapshot_manifest.json"
    quality_logical = "inputs/quality.json"
    if any(logical not in current.artifact_bindings for logical in (manifest_logical, quality_logical)):
        return ("Frozen research qualifications are not yet available.",)
    manifest_doc = _read_quality_bound_document(
        run_root=run_root, current=current, logical=manifest_logical,
        maximum_size=_session.QUALITY_FILE_LIMITS[manifest_logical],
    )
    quality_doc = _read_quality_bound_document(
        run_root=run_root, current=current, logical=quality_logical,
        maximum_size=_session.QUALITY_FILE_LIMITS[quality_logical],
    )
    manifest = validate_input_snapshot_manifest_document(manifest_doc)
    if manifest.document.content_sha256 != current.input_snapshot_manifest_sha256:
        raise SessionConflictError("live_start_manifest_binding_changed")
    quality = quality_doc.to_value()
    binding = next((row for row in manifest.blobs if row.name == "quality_inputs"), None)
    if (not isinstance(quality, dict) or set(quality) != QUALITY_INPUT_FIELDS
        or binding is None or binding.sha256 != _sha256_bytes(quality_doc.canonical_json)
        or binding.size_bytes != len(quality_doc.canonical_json) or binding.record_count != 1
        or quality["research_request_sha256"] != current.research_binding["request_sha256"]):
        raise SessionConflictError("live_start_quality_input_changed")
    research = validate_research_result(quality["research_result"], card_ids=None)
    context_doc = _read_quality_bound_document(
        run_root=run_root, current=current, logical="starter/starter_context.json",
        maximum_size=STARTER_CONTEXT_MAX_BYTES,
    )
    if context_doc is None:
        return _visible_research_limitations(research["limitations"])
    context = validate_starter_context_document(_quality_starter_document(context_doc))
    value = context.document.to_value()
    if (value["input_snapshot_manifest_sha256"] != manifest.document.content_sha256
        or FrozenJsonDocument.from_value(value["research_evidence"]).canonical_json
        != FrozenJsonDocument.from_value(research).canonical_json):
        raise SessionConflictError("live_start_quality_context_binding_changed")
    review = _quality_bound_review(run_root=run_root, current=current, context=context)
    return _starter_context_limitations(value, review=review)


def _quality_summary_runtime_write_state(current: LiveStartSession) -> str:
    intent = current.result_intent
    if current.terminal_status in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}:
        return "yes"
    if isinstance(intent, Mapping):
        disposition = intent.get("physical_disposition")
        if disposition == "COMMITTED":
            return "yes"
        if disposition == "NOT_COMMITTED":
            return "no"
        if disposition in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }:
            return "unknown"
    pending = current.pending_transition
    apply_pending = (
        isinstance(pending, Mapping)
        and pending.get("operation") == "install_apply_invocation"
    )
    if (
        current.apply_invocation_sha256 is not None
        or current.runtime_admission_binding is not None
        or current.apply_recovery is not None
        or apply_pending
        or current.phase
        in {
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        }
    ):
        return "unknown"
    return "no"


def _quality_summary_route(current: LiveStartSession) -> tuple[str, str]:
    if current.terminal_status in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}:
        return "result/summary.json", "use_installed_configuration"
    if current.terminal_status == "PREVIEW_READY":
        return "result/summary.json", "inspect_preserved_preview"
    if current.terminal_status == "APPLIED_BUT_NOT_VERIFIED":
        return "result/summary.json", "resume_existing_recovery"
    intent = current.result_intent
    if current.terminal_status is not None and (
        current.apply_invocation_sha256 is not None
        or current.runtime_admission_binding is not None
        or current.apply_recovery is not None
        or getattr(current, "closed_apply_recovery_commitment", None) is not None
        or (
            isinstance(intent, Mapping)
            and intent.get("physical_disposition")
            in {
                "NOT_COMMITTED",
                "COMMITTED_RECOVERY_PENDING",
                "UNKNOWN_REQUIRES_RECOVERY",
            }
        )
    ):
        return "result/summary.json", "resume_existing_recovery"
    if current.terminal_status is not None:
        review_phases = {
            "candidate_document_invalid": {
                LiveStartPhase.INPUT_FROZEN, LiveStartPhase.CANDIDATE_DRAFTED,
            },
            "candidate_revision_invalid": {
                LiveStartPhase.INPUT_FROZEN, LiveStartPhase.CANDIDATE_DRAFTED,
            },
            "review_document_invalid": {LiveStartPhase.CANDIDATE_VALIDATED},
            "revision_budget_exhausted": {
                LiveStartPhase.CANDIDATE_DRAFTED, LiveStartPhase.CANDIDATE_VALIDATED,
            },
        }
        error_code = intent.get("error_code") if isinstance(intent, Mapping) else None
        next_action = (
            "inspect_preserved_review_finding"
            if current.phase in review_phases.get(error_code, ())
            else "inspect_preserved_failure"
        )
        return "result/summary.json", next_action
    pending = current.pending_transition
    if (
        current.apply_invocation_sha256 is not None
        or current.runtime_admission_binding is not None
        or current.apply_recovery is not None
        or (
            isinstance(pending, Mapping)
            and pending.get("operation") == "install_apply_invocation"
        )
        or current.phase
        in {
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        }
    ):
        return "receipts/apply_invocation.json", "resume_existing_recovery"
    if current.phase is LiveStartPhase.DISCOVERY_REQUIRED:
        return "research/request.json", "complete_or_resume_same_research_request"
    if current.phase is LiveStartPhase.INPUT_FROZEN:
        return "inputs/input_snapshot_manifest.json", "dispatch_lead_strategist"
    if current.phase is LiveStartPhase.CANDIDATE_VALIDATED:
        return "receipts/candidate_validation.json", "dispatch_independent_reviewer"
    if current.phase is LiveStartPhase.CANDIDATE_DRAFTED:
        logical = (
            "starter/starter_config_review.json"
            if "starter/starter_config_review.json" in current.artifact_bindings
            else "starter/starter_config_candidate.json"
        )
        return logical, "return_exact_findings_to_same_lead"
    return "receipts/review_validation.json", "finalize_reviewed_candidate"


def quality_start_summary(*, run_root: Path) -> FrozenJsonDocument:
    """Project one read-only next action from a validated persisted session."""

    root = Path(run_root)
    current = _session.load_live_start_session_snapshot(root)
    if current.schema_version == 1:
        if current.terminal_status is not None:
            raw = _read_plain_bytes(
                root / "result/summary.json",
                maximum_size=_session.LIVE_START_RESULT_SUMMARY_MAX_BYTES,
            )
            return FrozenJsonDocument.from_json_bytes(raw)
        return _sealed_diagnostic(
            {
                "schema_version": 1,
                "diagnostic_kind": "live_start_resume",
                "status": current.phase.value,
                "run_root": str(root),
                "phase": current.phase.value,
                "candidate_revision": current.candidate_revision,
                "revisions_used": current.revisions_used,
                "findings": [],
            }
        )
    if current.schema_version != 2:
        raise SessionConflictError("live_start_quality_summary_version_invalid")
    progress = _quality_summary_progress(run_root=root, current=current)
    logical, next_action = _quality_summary_route(current)
    artifact_digest = current.artifact_bindings.get(logical)
    if artifact_digest is None:
        if logical == "receipts/apply_invocation.json":
            logical = "session.json"
            artifact_digest = _sha256_bytes(current.canonical_json)
        else:
            raise SessionConflictError(
                "live_start_quality_summary_artifact_missing"
            )
    draft = progress["draft"]
    urls = [] if draft is None else draft["urls"]
    source_records = progress["source_records"]
    limitations = list(_quality_available_limitations(run_root=root, current=current, progress=progress))
    return _sealed_diagnostic(
        {
            "schema_version": 2,
            "diagnostic_kind": "quality_live_start_route",
            "status": current.terminal_status or current.phase.value,
            "deck_name": current.deck_name,
            "phase": current.phase.value,
            "preserved_artifact": {
                "path": str(root / logical),
                "sha256": artifact_digest,
            },
            "acquisition_budget": {
                "search_query_limit": _QUALITY_RESEARCH_QUERY_LIMIT,
                "search_queries_reserved_unknown": len(progress["search_slots"]),
                "search_queries_remaining": 0,
                "page_url_limit": _QUALITY_RESEARCH_URL_LIMIT,
                "page_urls_admitted": len(urls),
                "resume_resets_budget": False,
            },
            "revision_budget": {
                "maximum": _QUALITY_REVISION_LIMIT,
                "used": current.revisions_used,
                "remaining": max(0, _QUALITY_REVISION_LIMIT - current.revisions_used),
            },
            "source_evidence": "bounded" if source_records else "limited",
            "visible_limitations": limitations,
            "runtime_write_state": _quality_summary_runtime_write_state(current),
            "next_action": next_action,
        }
    )


def _quality_fault(_point: str) -> None:
    """Deterministic crash-injection seam; never an authority or write bypass."""


def _quality_checkpoint(*, session_lease, current, changes):
    def fault(point):
        if changes.get("phase") == "INPUT_FROZEN" and point == "temp_flushed":
            _quality_fault("during_input_frozen_transition")

    return _session._transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=current,
        event="quality_transition",
        changes=changes,
        fault_hook=fault,
    )


def _quality_materialize(*, session_root, current, row):
    target = session_root / row["logical_path"]
    source = Path(row["source_path"])
    parent = _require_or_create_plain_child(session_root, target.parent.name)
    maximum = _session.QUALITY_FILE_LIMITS[row["logical_path"]]
    if path_lexists(target):
        raw = _read_plain_bytes(target, maximum_size=maximum)
        if len(raw) == row["size"] and _sha256_bytes(raw) == row["sha256"]:
            return
        if _sha256_bytes(raw) != current.artifact_bindings.get(row["logical_path"]):
            raise SessionConflictError("live_start_quality_target_changed")
        predecessor_identity, predecessor_sha256 = (
            path_identity(target),
            _sha256_bytes(raw),
        )
    else:
        if row["logical_path"] in current.artifact_bindings:
            raise SessionConflictError("live_start_quality_predecessor_missing")
        predecessor_identity = predecessor_sha256 = None
    payload = _read_plain_bytes(source, maximum_size=maximum)
    if (
        path_identity(source) != tuple(row["source_identity"])
        or path_identity(source.parent) != tuple(row["source_parent_identity"])
        or len(payload) != row["size"]
        or _sha256_bytes(payload) != row["sha256"]
    ):
        raise SessionConflictError("live_start_quality_staging_changed")
    if source.parent == target.parent:
        from hsconfig.atomic_io import _flush_parent_directory

        secure_replace(
            source,
            target,
            expected_source_identity=tuple(row["source_identity"]),
            expected_source_parent_identity=path_identity(parent),
            expected_target_parent_identity=path_identity(parent),
            expected_target_identity=predecessor_identity,
            expected_target_absent=predecessor_identity is None,
        )
        _flush_parent_directory(parent)
    else:
        reserved = target.with_name(f".{target.name}.live-start-atomic.tmp")
        if path_lexists(reserved):
            secure_unlink(
                reserved,
                expected_identity=path_identity(reserved),
                expected_parent_identity=path_identity(parent),
                missing_ok=False,
            )
        atomic_write_reserved_bytes(
            path=target,
            payload=payload,
            expected_parent_identity=path_identity(parent),
            expected_predecessor_identity=predecessor_identity,
            expected_predecessor_sha256=predecessor_sha256,
            maximum_size=maximum,
        )
    if _read_plain_bytes(target, maximum_size=maximum) != payload:
        raise SessionConflictError("live_start_quality_install_readback_failed")


def _continue_quality_documents(*, session_lease, current):
    pending = current.pending_transition
    if pending is None or pending.get("operation") not in _session._QUALITY_OPERATIONS:
        return current
    root = session_lease.session_root
    if pending["stage"] == "PREPARED":
        value = _session._thaw(pending)
        value["stage"] = "PRIMARY_APPLIED"
        current = _quality_checkpoint(
            session_lease=session_lease,
            current=current,
            changes={"pending_transition": _session._seal_pending(value)},
        )
    rows = _session._quality_pending_rows(session=current, root=root)
    while current.pending_transition["next_action_index"] < len(rows):
        index = current.pending_transition["next_action_index"]
        row = rows[index]
        _quality_materialize(session_root=root, current=current, row=row)
        point = {
            "inputs/quality_seed.json": "after_seed_install",
            "research/request.json": "after_request_install",
        }.get(row["logical_path"])
        if point:
            _quality_fault(point)
        value = _session._thaw(current.pending_transition)
        value["next_action_index"] += 1
        current = _quality_checkpoint(
            session_lease=session_lease,
            current=current,
            changes={"pending_transition": _session._seal_pending(value)},
        )
    _session._validate_starter_document_postconditions(
        session_lease=session_lease, session=current, complete=True
    )
    changes = {
        "pending_transition": None,
        "artifact_bindings": dict(
            current.pending_transition["successor_artifact_bindings"]
        ),
    }
    if current.pending_transition["operation"] == "quality_freeze":
        frozen = _load_frozen_compiler_inputs(root, rebind_operator=False)
        _quality_fault("after_final_input_installation")
        changes.update(
            {
                "phase": "INPUT_FROZEN",
                "input_snapshot_manifest_sha256": frozen.manifest.document.content_sha256,
            }
        )
    return _quality_checkpoint(
        session_lease=session_lease, current=current, changes=changes
    )


def _install_quality_documents(*, session_lease, current, operation, documents):
    root = session_lease.session_root
    actions = []
    for logical, payload in sorted(documents.items()):
        source = _write_external_authority_source(
            session_root=root,
            name=f"{operation}-{_sha256_bytes(payload)[7:]}-{Path(logical).name}",
            payload=payload,
        )
        actions.append(
            _session._quality_action(logical=logical, source=source, payload=payload)
        )
    pending = _session._empty_pending_transition(
        session=current, operation=operation, external_file_action=None
    )
    successor = dict(current.artifact_bindings)
    successor.update({row["logical_path"]: row["sha256"] for row in actions})
    pending.update(
        {
            "actions": actions,
            "successor_artifact_bindings": successor,
            "target_phase": "INPUT_FROZEN"
            if operation == "quality_freeze"
            else "DISCOVERY_REQUIRED",
        }
    )
    current = _quality_checkpoint(
        session_lease=session_lease,
        current=current,
        changes={"pending_transition": _session._seal_pending(pending)},
    )
    return _continue_quality_documents(session_lease=session_lease, current=current)


def _load_quality_state(*, root, current, profile):
    from hsconfig.card_snapshot import validated_card_snapshot
    from hsconfig.input_snapshot_manifest import _operator_bindings_from_values
    from hsconfig.live_start_research import (
        validate_research_attempts,
        validate_research_draft,
        validate_research_request,
    )

    def read(logical):
        raw = _read_plain_bytes(
            root / logical, maximum_size=_session.QUALITY_FILE_LIMITS[logical]
        )
        if _sha256_bytes(raw) != current.artifact_bindings[logical]:
            raise SessionConflictError("live_start_quality_input_changed")
        doc = FrozenJsonDocument.from_json_bytes(raw)
        if doc.canonical_json != raw:
            raise SessionConflictError("live_start_quality_input_noncanonical")
        return doc.to_value()

    seed, deck, cards = (
        read(path)
        for path in (
            "inputs/quality_seed.json",
            "inputs/deck.json",
            "inputs/cards.json",
        )
    )
    expected_seed = {
        "schema_version",
        "bound_date",
        "operator_bindings",
        "baseline_receipt",
        "policy_profile",
        "card_snapshot_sha256",
        "card_snapshot_captured_at",
        "card_snapshot_upstream_version",
    }
    if (
        set(seed) != expected_seed
        or type(seed["schema_version"]) is not int
        or seed["schema_version"] != 1
    ):
        raise SessionConflictError("live_start_quality_seed_invalid")
    output = derive_deck_output_binding(profile, current.deck_name)
    if seed["operator_bindings"] != _operator_bindings_from_values(
        operator_profile=profile,
        deck_output_binding=output,
        deck_name=current.deck_name,
    ):
        raise SessionConflictError("live_start_quality_profile_changed")
    snapshot = FrozenJsonDocument.from_value(
        {
            "full_cards": cards["full_cards"],
            "collectible_cards": cards["collectible_cards"],
            "dbf_to_card_id": {
                str(row["dbf_id"]): row["id"]
                for row in cards["full_cards"]
                if row.get("dbf_id") is not None
            },
            "captured_at": seed["card_snapshot_captured_at"],
            "upstream_version": seed["card_snapshot_upstream_version"],
            "dataset_sha256": seed["card_snapshot_sha256"],
        }
    )
    snapshot_value = validated_card_snapshot(snapshot)
    if (
        snapshot_value["dataset_sha256"] != seed["card_snapshot_sha256"]
        or snapshot_value["collectible_cards"] != cards["collectible_cards"]
    ):
        raise SessionConflictError("live_start_quality_snapshot_changed")
    _validate_deck_and_card_closure(
        deck,
        full_cards=cards["full_cards"],
        collectible_cards=cards["collectible_cards"],
    )
    request = read("research/request.json")
    try:
        checked_request = validate_research_request(
            request,
            run_id=current.run_id,
            deck_identity=deck["deck_identity"],
            captured_input_sha256=current.research_binding["seed_sha256"],
        )
    except ValueError:
        raise SessionConflictError("live_start_quality_request_changed") from None
    if (
        checked_request.to_value()["content_sha256"]
        != current.research_binding["request_sha256"]
    ):
        raise SessionConflictError("live_start_quality_request_changed")
    progress = read("research/progress.json")
    if (
        set(progress)
        != {
            "schema_version",
            "request_sha256",
            "search_slots",
            "draft",
            "deadline_utc",
            "attempts",
            "source_records",
            "source_acquisition_reports",
        }
        or type(progress["schema_version"]) is not int
        or progress["schema_version"] != 1
        or progress["request_sha256"] != request["content_sha256"]
        or progress["search_slots"]
        != [
            {"query": query, "state": "reserved_unknown"}
            for query in request["queries"]
        ]
    ):
        raise SessionConflictError("live_start_quality_progress_invalid")
    if progress["draft"] is not None:
        urls, _ = validate_research_draft(
            progress["draft"], request_sha256=request["content_sha256"]
        )
        if any(attempt.get("url") not in urls for attempt in progress["attempts"]):
            raise SessionConflictError("live_start_quality_unadmitted_attempt")
    elif (
        any(
            progress[key]
            for key in ("attempts", "source_records", "source_acquisition_reports")
        )
        or progress["deadline_utc"] is not None
    ):
        raise SessionConflictError("live_start_quality_attempt_before_draft")
    validate_research_attempts(
        acquired={"source_records": progress["source_records"]},
        discovery_outcome=(progress["draft"] or {}).get(
            "discovery_outcome", "unavailable"
        ),
        attempts=progress["attempts"],
        deadline_utc=progress["deadline_utc"],
    )
    return seed, deck, cards, snapshot, request, progress, output


def _quality_preparation(*, root):
    frozen = _load_frozen_compiler_inputs(root, rebind_operator=False)
    context = build_quality_starter_context(frozen)
    path = _materialize_starter_context(
        local_app_data_root=root.parent.parent.parent,
        run_id=root.name,
        payload=context.document.canonical_json,
    )
    value = context.document.to_value()
    return LiveStartPreparation(
        run_root=root,
        starter_context_path=path,
        candidate_revision=1,
        visible_limitations=_starter_context_limitations(value),
    )


def _finish_quality_inputs(
    *, session_lease, current, profile, state, acquisition_budget_exhausted=False
):
    from hsconfig.starter_card_facts import project_card_facts
    from hsconfig.live_start_research import (
        build_research_result,
        compile_research_sources,
    )
    from hsconfig.internal_source_authority import split_source_documents_handoff

    seed, deck, cards, snapshot, request, progress, output = state
    acquired = {
        "source_records": progress["source_records"],
        "source_acquisition_report": {
            "reports": progress["source_acquisition_reports"],
            "search_slots": progress["search_slots"],
        },
    }
    compiled, handoff = compile_research_sources(
        acquired=acquired,
        deck_identity=deck["deck_identity"],
        current_date=seed["bound_date"],
    )
    _research_handoff, handoff = split_source_documents_handoff(handoff)
    facts = project_card_facts(deck["deck_identity"], cards["full_cards"])
    research = build_research_result(
        acquired=compiled.to_value(),
        discovery_outcome=progress["draft"]["discovery_outcome"],
        attempts=progress["attempts"],
        deadline_utc=progress["deadline_utc"],
        card_metadata=facts["card_metadata"],
        acquisition_budget_exhausted=acquisition_budget_exhausted,
    )
    quality = FrozenJsonDocument.from_value(
        {
            key: seed[key]
            for key in (
                "card_snapshot_sha256",
                "card_snapshot_captured_at",
                "card_snapshot_upstream_version",
            )
        }
        | {
            "research_request_sha256": request["content_sha256"],
            "research_result": research.to_value(),
        }
    )
    arguments = argparse.Namespace(
        command="prepare",
        deck_name=current.deck_name,
        deck_code=deck["cards_payload"]["deck_code"],
        out=str(output.output_root),
        runtime_root=str(profile.runtime_root),
        guide_sources_json=None,
        source_documents_json=None,
        auto_research_fallback=False,
        json=True,
        cards_json=None,
        claims_json=None,
        plan_reports_dir=None,
        allow_placeholder=False,
        current_date=seed["bound_date"],
        collectible_cards_json=None,
        full_cards_json=None,
        skip_semantic_fetch=False,
        source_evidence_json=None,
    )
    preconfig = build_preconfig_context(
        arguments,
        current_date=date.fromisoformat(seed["bound_date"]),
        source_authority_handoff=handoff,
        source_authority_consumer="prepare",
        load_cards_fn=lambda *_args, **_kwargs: deepcopy(deck["cards_payload"]),
        fetch_latest_cards_fn=lambda **_: deepcopy(cards["full_cards"]),
        fetch_latest_collectible_cards_fn=lambda **_: deepcopy(
            cards["collectible_cards"]
        ),
    )
    preconfig.update(
        {
            "policy_profile": seed["policy_profile"],
            "globalvalues_baseline": cards["globalvalues_baseline"],
            "globalvalues_baseline_receipt": seed["baseline_receipt"],
        }
    )
    frozen = freeze_compiler_inputs(
        snapshot=PackageResolutionSnapshot.from_preconfig(preconfig),
        deck=deck,
        full_cards=cards["full_cards"],
        collectible_cards=cards["collectible_cards"],
        source_acquisition={
            "guide_builder_receipt": preconfig["guide_builder_receipt"],
            "source_evidence_report": preconfig["source_evidence_report"],
            "policy_profile": seed["policy_profile"],
        },
        source_documents={"guide_sources": preconfig["guide_sources_generated"]},
        globalvalues_baseline=cards["globalvalues_baseline"],
        bound_date=seed["bound_date"],
        runtime_grammar_version=_RUNTIME_GRAMMAR_VERSION,
        compiler_contract_id="hsconfig-live-start-v2",
        operator_profile=profile,
        deck_output_binding=output,
        quality_inputs=quality,
    )
    sources = FrozenJsonDocument.from_value(
        {
            "source_acquisition": frozen.source_acquisition.to_value(),
            "source_documents": frozen.source_documents.to_value(),
        }
    )
    _install_quality_documents(
        session_lease=session_lease,
        current=current,
        operation="quality_freeze",
        documents={
            "inputs/quality.json": quality.canonical_json,
            "inputs/sources.json": sources.canonical_json,
            "inputs/input_snapshot_manifest.json": frozen.manifest.document.canonical_json,
        },
    )
    return _quality_preparation(root=session_lease.session_root)


def _quality_research_under_lock(*, session_lease, current, draft_path=None):
    from hsconfig.input_snapshot_manifest import _operator_bindings_from_values
    from hsconfig.live_start_research import validate_research_draft, research_timeout
    from hsconfig.source_acquisition import collect_public_source_records

    root = session_lease.session_root
    if (
        current.schema_version != 2
        or current.phase is not LiveStartPhase.DISCOVERY_REQUIRED
    ):
        raise SessionConflictError("live_start_quality_discovery_required")
    profile = load_operator_profile()
    with lease_operator_profile(expected_profile=profile):
        # Seed identity remains authoritative even when the final input CAS
        # interrupted after physically installing its successor documents.
        if "inputs/quality_seed.json" in current.artifact_bindings:
            seed_raw = _read_plain_bytes(
                root / "inputs/quality_seed.json", maximum_size=128 * 1024
            )
            if _sha256_bytes(seed_raw) != current.research_binding["seed_sha256"]:
                raise SessionConflictError("live_start_quality_seed_changed")
            seed = FrozenJsonDocument.from_json_bytes(seed_raw).to_value()
            output = derive_deck_output_binding(profile, current.deck_name)
            if seed["operator_bindings"] != _operator_bindings_from_values(
                operator_profile=profile,
                deck_output_binding=output,
                deck_name=current.deck_name,
            ):
                raise SessionConflictError("live_start_quality_profile_changed")
        current = _continue_quality_documents(
            session_lease=session_lease, current=current
        )
        if current.phase is LiveStartPhase.INPUT_FROZEN:
            return _quality_preparation(root=root)
        state = _load_quality_state(root=root, current=current, profile=profile)
        seed, deck, cards, snapshot, request, progress, output = state
        if draft_path is not None:
            draft = _load_unsigned_draft(draft_path, maximum_size=32 * 1024)
            validate_research_draft(draft, request_sha256=request["content_sha256"])
            if progress["draft"] is not None and progress["draft"] != draft:
                raise SessionConflictError("live_start_quality_draft_already_admitted")
            if progress["draft"] is None:
                progress["draft"] = draft
                current = _install_quality_documents(
                    session_lease=session_lease,
                    current=current,
                    operation="quality_progress",
                    documents={
                        "research/progress.json": FrozenJsonDocument.from_value(
                            progress
                        ).canonical_json
                    },
                )
        if progress["draft"] is None:
            return LiveStartDiscovery(
                root, root / "research/request.json", request["content_sha256"]
            )
        urls, _ = validate_research_draft(
            progress["draft"], request_sha256=request["content_sha256"]
        )
        interrupted = False
        for attempt in progress["attempts"]:
            if attempt["state"] == "started":
                attempt.update({"state": "interrupted", "error": "interrupted"})
                interrupted = True
        if interrupted:
            current = _install_quality_documents(
                session_lease=session_lease,
                current=current,
                operation="quality_progress",
                documents={
                    "research/progress.json": FrozenJsonDocument.from_value(
                        progress
                    ).canonical_json
                },
            )
        acquisition_budget_exhausted = False
        for url in urls:
            if url in {row["url"] for row in progress["attempts"]}:
                continue
            if progress["deadline_utc"] is None:
                progress["deadline_utc"] = time.time() + 30.0
            timeout = research_timeout(
                deadline_utc=progress["deadline_utc"], now_utc=time.time()
            )
            if timeout <= 0:
                acquisition_budget_exhausted = True
                break
            attempt = {
                "url": url,
                "state": "started",
                "record_sha256": None,
                "error": None,
            }
            progress["attempts"].append(attempt)
            current = _install_quality_documents(
                session_lease=session_lease,
                current=current,
                operation="quality_progress",
                documents={
                    "research/progress.json": FrozenJsonDocument.from_value(
                        progress
                    ).canonical_json
                },
            )
            _quality_fault("after_started_attempt_checkpoint")
            acquired = collect_public_source_records(
                deck_name=current.deck_name,
                deck_identity=deck["deck_identity"],
                source_urls=[url],
                current_date=seed["bound_date"],
                timeout_seconds=timeout,
                deadline_utc=progress["deadline_utc"],
                card_snapshot=snapshot,
            )
            records = acquired["source_records"]
            if records:
                if len(records) != 1 or records[0]["source_url"] != url:
                    raise SessionConflictError(
                        "live_start_quality_collector_scope_invalid"
                    )
                progress["source_records"].append(records[0])
                attempt.update(
                    {
                        "state": "completed",
                        "record_sha256": _sha256_bytes(
                            FrozenJsonDocument.from_value(records[0]).canonical_json
                        ),
                    }
                )
            else:
                report = acquired.get("source_acquisition_report", {})
                failures = report.get("failures", []) if isinstance(report, dict) else []
                error = next(
                    (
                        row["error"]
                        for row in failures
                        if isinstance(row, dict)
                        and row.get("url") == url
                        and isinstance(row.get("error"), str)
                        and row["error"]
                    ),
                    "page_acquisition_failed",
                )
                attempt.update({"state": "failed", "error": error})
            progress["source_acquisition_reports"].append(
                acquired.get("source_acquisition_report", {})
            )
            current = _install_quality_documents(
                session_lease=session_lease,
                current=current,
                operation="quality_progress",
                documents={
                    "research/progress.json": FrozenJsonDocument.from_value(
                        progress
                    ).canonical_json
                },
            )
            _quality_fault("after_fetched_record_persistence")
        state = _load_quality_state(root=root, current=current, profile=profile)
        return _finish_quality_inputs(
            session_lease=session_lease,
            current=current,
            profile=profile,
            state=state,
            acquisition_budget_exhausted=acquisition_budget_exhausted,
        )


def complete_live_start_research(
    *, session_root: Path, draft_path: Path
) -> LiveStartPreparation | LiveStartResult:
    """Admit one bounded shortlist, journal acquisition, and freeze exact inputs."""
    with _session.lease_live_start_session(Path(session_root)) as lease:
        current = _session.load_live_start_session_under_lock(session_lease=lease)
        return _quality_research_under_lock(
            session_lease=lease, current=current, draft_path=draft_path
        )


def _resume_quality_discovery(
    *, current: LiveStartSession, session_root: Path
) -> LiveStartDiscovery | LiveStartPreparation | LiveStartResult:
    with _session.lease_live_start_session(session_root) as lease:
        observed = _session.load_live_start_session_under_lock(session_lease=lease)
        if observed.content_sha256 != current.content_sha256:
            raise SessionConflictError("live_start_quality_resume_changed")
        return _quality_research_under_lock(session_lease=lease, current=observed)


def prepare_quality_live_start(
    request: LiveStartRequest,
) -> LiveStartDiscovery | LiveStartResult:
    from hsconfig.card_snapshot import validated_card_snapshot
    from hsconfig.deckstring_decode import decode_deck_code_from_snapshot
    from hsconfig.deck_identity import normalize_roster, stable_deck_fingerprint
    from hsconfig.input_snapshot_manifest import _operator_bindings_from_values
    from hsconfig.live_start_research import build_research_request

    try:
        _validate_live_start_request(request)
    except (TypeError, ValueError):
        return _pre_session_result(
            status="FAILED_PRESERVED",
            deck_name=getattr(request, "deck_name", None),
            error_code="deck_or_input_invalid",
        )
    try:
        profile = load_operator_profile()
        revalidate_operator_profile(profile)
        if not profile.live_by_default and not request.preview_requested:
            raise ValueError("operator_profile_live_disabled")
        output = derive_deck_output_binding(profile, request.deck_name)
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return _pre_session_result(
            status="PROFILE_REQUIRED",
            deck_name=request.deck_name,
            error_code="operator_profile_required",
        )
    failure_code = "operator_profile_changed"
    try:
        with lease_operator_profile(expected_profile=profile):
            failure_code = "card_snapshot_unavailable"
            try:
                snapshot = fetch_card_snapshot(timeout=10.0)
            except (
                SessionCapabilityError, SessionConflictError,
                _session.SessionValidationError,
            ):
                raise
            except (TypeError, ValueError):
                failure_code = "card_snapshot_invalid"
                raise
            failure_code = "card_snapshot_invalid"
            captured = validated_card_snapshot(snapshot)
            failure_code = "deck_or_input_invalid"
            decoded = decode_deck_code_from_snapshot(request.deck_code, snapshot)
            if decoded["hero"]["type"] != "HERO":
                raise ValueError("live_start_deck_code_invalid")
            payload = {
                key: decoded[key]
                for key in (
                    "cards",
                    "hero_dbf_id",
                    "format",
                    "sideboards",
                    "deckstring_decode_receipt",
                    "card_id_map",
                )
            } | {"card_source": "deckstring"}
            # Task2 has resolved these exact deckstring DBFs from this snapshot.
            # The legacy verifier re-decodes with local cardxml and is not applicable.
            payload["deck_input_verification"] = {
                "status": "decoded_from_deck_code",
                "runtime_apply_eligible": True,
                "normalized_roster_sha256": "sha256:"
                + stable_deck_fingerprint(normalize_roster(decoded["cards"])),
            }
            payload["deck_code"] = request.deck_code
            identity = build_deck_identity(
                deck_name=request.deck_name,
                deck_code=request.deck_code,
                cards=payload["cards"],
                hero_dbf_id=payload["hero_dbf_id"],
                format=payload["format"],
                sideboards=payload["sideboards"],
            )
            deck = FrozenJsonDocument.from_value(
                {"cards_payload": payload, "deck_identity": identity}
            )
            _validate_deck_and_card_closure(
                deck.to_value(),
                full_cards=captured["full_cards"],
                collectible_cards=captured["collectible_cards"],
            )
            failure_code = "runtime_baseline_unavailable"
            baseline_receipt = load_globalvalues_baseline(profile.runtime_root)
            baseline = normalize_globalvalues_decision_baseline(
                baseline_receipt["baseline"]
            )
            failure_code = "input_snapshot_invalid"
            cards = FrozenJsonDocument.from_value(
                {
                    "full_cards": captured["full_cards"],
                    "collectible_cards": captured["collectible_cards"],
                    "globalvalues_baseline": baseline,
                }
            )
            seed = FrozenJsonDocument.from_value(
                {
                    "schema_version": 1,
                    "bound_date": date.today().isoformat(),
                    "operator_bindings": _operator_bindings_from_values(
                        operator_profile=profile,
                        deck_output_binding=output,
                        deck_name=request.deck_name,
                    ),
                    "baseline_receipt": baseline_receipt,
                    "policy_profile": _policy_profile_value(),
                    "card_snapshot_sha256": captured["dataset_sha256"],
                    "card_snapshot_captured_at": captured["captured_at"],
                    "card_snapshot_upstream_version": captured["upstream_version"],
                }
            )
            failure_code = "operator_profile_changed"
    except (SessionCapabilityError, SessionConflictError, _session.SessionValidationError):
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        return _pre_session_result(
            status="FAILED_PRESERVED",
            deck_name=request.deck_name,
            error_code=failure_code,
        )
    run_id = secrets.token_hex(16)
    root = Path(os.environ["LOCALAPPDATA"]) / "HSConfig" / "runs" / run_id
    hero = next(
        row
        for row in captured["full_cards"]
        if row["id"] == captured["dbf_to_card_id"][str(payload["hero_dbf_id"])]
    )
    query_identity = {
        **identity,
        "class": hero.get("card_class", ""),
        "cards": [
            {
                **card,
                "name": next(
                    (
                        row.get("name", "")
                        for row in captured["full_cards"]
                        if row["id"] == card["card_id"]
                    ),
                    "",
                ),
            }
            for card in identity["cards"]
        ],
    }
    queries = tuple(
        build_research_request(
            run_id=run_id,
            deck_identity=query_identity,
            captured_input_sha256=_sha256_bytes(seed.canonical_json),
            queries=(),
        ).to_value()["queries"]
    )
    research = build_research_request(
        run_id=run_id,
        deck_identity=identity,
        captured_input_sha256=_sha256_bytes(seed.canonical_json),
        queries=queries,
    )
    progress = FrozenJsonDocument.from_value(
        {
            "schema_version": 1,
            "request_sha256": research.to_value()["content_sha256"],
            "search_slots": [
                {"query": query, "state": "reserved_unknown"} for query in queries
            ],
            "draft": None,
            "deadline_utc": None,
            "attempts": [],
            "source_records": [],
            "source_acquisition_reports": [],
        }
    )
    _session.create_live_start_session(
        session_root=root,
        repository_root=Path(__file__).resolve().parents[2],
        runtime_root=profile.runtime_root,
        output_base_root=profile.output_base_root,
        output_deck_root=output.output_root,
        installed_skill_root=Path.home() / ".codex" / "skills" / "hsconfig",
        deck_name=request.deck_name,
        deck_code_sha256="sha256:" + sha256(request.deck_code.encode()).hexdigest(),
        preview_requested=request.preview_requested,
        _quality_documents={
            "inputs/deck.json": deck.canonical_json,
            "inputs/cards.json": cards.canonical_json,
            "inputs/quality_seed.json": seed.canonical_json,
            "research/request.json": research.canonical_json,
            "research/progress.json": progress.canonical_json,
        },
        _research_binding={
            "request_sha256": research.to_value()["content_sha256"],
            "seed_sha256": _sha256_bytes(seed.canonical_json),
            "deck_sha256": _sha256_bytes(deck.canonical_json),
            "cards_sha256": _sha256_bytes(cards.canonical_json),
        },
        _fault_hook=_quality_fault,
    )
    with _session.lease_live_start_session(root) as lease:
        current = _session.load_live_start_session_under_lock(session_lease=lease)
        with lease_operator_profile(expected_profile=profile):
            _continue_quality_documents(session_lease=lease, current=current)
    return LiveStartDiscovery(
        root, root / "research/request.json", research.to_value()["content_sha256"]
    )


def prepare_live_start(
    request: LiveStartRequest,
) -> LiveStartDiscovery | LiveStartResult:
    return prepare_quality_live_start(request)


def _prepare_legacy_live_start(
    request: LiveStartRequest,
) -> LiveStartPreparation | LiveStartResult:
    """Freeze one fresh run and expose only its schema-2 strategy context."""

    try:
        _validate_live_start_request(request)
    except (TypeError, ValueError):
        deck_name = request.deck_name if isinstance(request, LiveStartRequest) else None
        return _pre_session_result(
            status="FAILED_PRESERVED",
            deck_name=deck_name,
            error_code="deck_or_input_invalid",
        )
    try:
        profile = load_operator_profile()
        revalidate_operator_profile(profile)
        if not profile.live_by_default and not request.preview_requested:
            raise ValueError("operator_profile_live_disabled")
        deck_output_binding = derive_deck_output_binding(
            profile,
            request.deck_name,
        )
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        return _pre_session_result(
            status="PROFILE_REQUIRED",
            deck_name=request.deck_name,
            error_code="operator_profile_required",
        )
    try:
        frozen = _capture_live_start_inputs(
            request,
            profile,
            deck_output_binding,
        )
    except (SessionCapabilityError, SessionConflictError, _session.SessionValidationError):
        raise
    except _LiveStartCaptureFailure as error:
        return _pre_session_result(
            status="FAILED_PRESERVED", deck_name=request.deck_name,
            error_code="deck_or_input_invalid", validated_deck=error.deck,
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return _pre_session_result(
            status="FAILED_PRESERVED",
            deck_name=request.deck_name,
            error_code="deck_or_input_invalid",
        )

    local_app_data_value = os.environ.get("LOCALAPPDATA")
    if not local_app_data_value:
        return _pre_session_result(
            status="FAILED_PRESERVED",
            deck_name=request.deck_name,
            error_code="deck_or_input_invalid",
        )
    local_app_data_root = Path(local_app_data_value)
    run_id = secrets.token_hex(16)
    run_root = local_app_data_root / "HSConfig" / "runs" / run_id
    deck_code_sha256 = "sha256:" + sha256(
        request.deck_code.encode("utf-8")
    ).hexdigest()
    created = None
    try:
        created = _session.create_live_start_session(
            session_root=run_root,
            local_app_data_root=local_app_data_root,
            repository_root=Path(__file__).resolve().parents[2],
            runtime_root=profile.runtime_root,
            output_base_root=profile.output_base_root,
            output_deck_root=deck_output_binding.output_root,
            installed_skill_root=Path.home() / ".codex" / "skills" / "hsconfig",
            deck_name=request.deck_name,
            deck_code_sha256=deck_code_sha256,
            preview_requested=request.preview_requested,
            frozen_compiler_inputs=frozen,
        )
        context = build_single_candidate_starter_context(frozen)
        context_path = _materialize_starter_context(
            local_app_data_root=local_app_data_root,
            run_id=created.run_id,
            payload=context.document.canonical_json,
        )
    except (SessionCapabilityError, SessionConflictError, _session.SessionValidationError):
        raise
    except (OSError, RuntimeError, TypeError, ValueError):
        if created is not None:
            with _session.lease_live_start_session(run_root) as session_lease:
                current = _session.load_live_start_session_under_lock(
                    session_lease=session_lease
                )
                return _terminalize_preapply_failure_under_lock(
                    session_lease=session_lease, current=current,
                    context=None, candidate=None,
                    error_code="deck_or_input_invalid",
                )
        if not run_root.exists():
            return _pre_session_result(
                status="FAILED_PRESERVED",
                deck_name=request.deck_name,
                error_code="deck_or_input_invalid",
            )
        raise
    return LiveStartPreparation(
        run_root=run_root,
        starter_context_path=context_path,
        candidate_revision=1,
        visible_limitations=_starter_context_limitations(
            context.document.to_value()
        ),
    )


def validate_live_start_candidate(
    *,
    session_root: Path,
    draft_path: Path,
) -> FrozenJsonDocument:
    """Seal, install, and validate one lead candidate for the current revision."""

    with _session.lease_live_start_session(Path(session_root)) as session_lease:
        current = _session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        if current.terminal_status is not None:
            return _load_terminal_result(
                session_root=session_lease.session_root,
                terminal=current,
            ).summary
        if current.phase is LiveStartPhase.INPUT_FROZEN:
            expected_revision = current.candidate_revision
            final_event = "initial_draft"
        elif (
            current.phase is LiveStartPhase.CANDIDATE_DRAFTED
            and current.revisions_used == current.candidate_revision
            and current.candidate_revision < 3
        ):
            expected_revision = current.candidate_revision + 1
            final_event = "replacement_draft"
        else:
            raise SessionConflictError("live_start_candidate_cursor_invalid")
        frozen = load_frozen_compiler_inputs(session_lease.session_root)
        version = _persisted_live_document_version(session_lease.session_root)
        context = (
            build_quality_starter_context(frozen)
            if version == 3
            else build_single_candidate_starter_context(frozen)
        )
        draft = _load_unsigned_draft(
            Path(draft_path),
            maximum_size=STARTER_CANDIDATE_MAX_BYTES,
        )
        try:
            candidate_document = seal_starter_document(
                draft,
                expected_fields=QUALITY_STARTER_CANDIDATE_FIELDS
                if version == 3
                else SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
                schema_version=version,
            )
        except (TypeError, ValueError):
            return _terminalize_preapply_failure_under_lock(
                session_lease=session_lease, current=current, context=context,
                candidate=None, error_code="candidate_document_invalid",
            ).summary
        if candidate_document.to_value()["candidate_revision"] != expected_revision:
            return _terminalize_preapply_failure_under_lock(
                session_lease=session_lease, current=current, context=context,
                candidate=None, error_code="candidate_revision_invalid",
            ).summary
        documents = {
            "starter/starter_config_candidate.json": (
                candidate_document.canonical_json
            )
        }
        if current.phase is LiveStartPhase.INPUT_FROZEN:
            documents["starter/starter_context.json"] = (
                context.document.canonical_json
            )
        current = _install_session_documents(
            session_lease=session_lease,
            current=current,
            operation="install_candidate",
            final_event=final_event,
            documents=documents,
        )
        _cursor, result = _validate_installed_candidate_under_lock(
            session_lease=session_lease, current=current, context=context
        )
        return result


def _candidate_validation_finding(*, session_root: Path) -> str | None:
    """Recheck the immutable candidate without charging or creating authority."""

    try:
        context = _load_bound_starter_context(session_root=session_root)
        candidate = _load_bound_candidate(session_root=session_root, context=context)
        if context.document.to_value()["schema_version"] == 3:
            from hsconfig.quality_candidate_admission import validate_quality_candidate_admission

            validate_quality_candidate_admission(candidate, context)
    except (TypeError, ValueError) as error:
        code = str(error)
        return code if code in STARTER_CANDIDATE_FINDING_CODES else "candidate_semantics_invalid"
    return None


def _candidate_revision_diagnostic(
    *, current: LiveStartSession, finding: str,
) -> FrozenJsonDocument:
    return _sealed_diagnostic({
        "schema_version": 1,
        "diagnostic_kind": "live_start_candidate_validation",
        "status": "revision_required",
        "candidate_revision": current.candidate_revision,
        "next_candidate_revision": current.candidate_revision + 1,
        "revisions_used": current.revisions_used,
        "findings": [finding],
    })


def _validate_installed_candidate_under_lock(
    *, session_lease: LiveStartSessionLease, current: LiveStartSession,
    context: StarterContext,
) -> tuple[LiveStartSession, FrozenJsonDocument]:
    if (current.phase is not LiveStartPhase.CANDIDATE_DRAFTED
        or current.pending_transition is not None
        or current.revisions_used >= current.candidate_revision):
        raise SessionConflictError("live_start_candidate_validation_cursor_invalid")
    finding = _candidate_validation_finding(session_root=session_lease.session_root)
    if finding is not None:
        if current.revisions_used < 2 and current.candidate_revision < 3:
            failed = _session.transition_live_start_session_under_lock(
                session_lease=session_lease, expected_session=current, event="technical_failure"
            )
            return failed, _candidate_revision_diagnostic(current=failed, finding=finding)
        result = _terminalize_preapply_failure_under_lock(
            session_lease=session_lease, current=current, context=context,
            candidate=None, error_code="revision_budget_exhausted",
        )
        return _session.load_live_start_session_under_lock(session_lease=session_lease), result.summary
    if current.schema_version == 2:
        from hsconfig.starter_review import build_candidate_review_facts

        candidate = _load_bound_candidate(
            session_root=session_lease.session_root, context=context
        )
        receipt = seal_starter_document(
            {
                "schema_version": 2,
                "receipt_kind": "candidate_validation",
                "run_id": current.run_id,
                "candidate_revision": current.candidate_revision,
                "starter_context_sha256": context.document.content_sha256,
                "candidate_sha256": candidate.document.content_sha256,
                "status": "valid",
                "findings": [],
                "review_facts": build_candidate_review_facts(
                    context=context, candidate=candidate
                ).to_value(),
            },
            expected_fields=QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
            schema_version=2,
        ).to_value()
    else:
        receipt = _session.seal_validation_receipt(
            receipt_kind="candidate_validation",
            unsigned_value={
                "run_id": current.run_id,
                "candidate_revision": current.candidate_revision,
                "starter_context_sha256": current.artifact_bindings[
                    "starter/starter_context.json"
                ],
                "candidate_sha256": current.artifact_bindings[
                    "starter/starter_config_candidate.json"
                ],
                "status": "valid",
                "findings": [],
            },
        )
    current = _install_session_documents(
        session_lease=session_lease, current=current,
        operation="install_candidate_validation", final_event="candidate_valid",
        documents={"receipts/candidate_validation.json": (
            FrozenJsonDocument.from_value(receipt).canonical_json + b"\n"
        )},
    )
    return current, FrozenJsonDocument.from_value(receipt)


def _review_revision_physical_step(
    *,
    current: LiveStartSession,
    action: str,
) -> _session.CandidateReviewRevisionPhysicalPostcondition:
    pending = current.pending_transition
    if not isinstance(pending, Mapping):
        raise SessionConflictError("live_start_review_revision_pending_missing")
    external = pending.get("external_file_action")
    if action != "retire_candidate_validation_receipt":
        if not isinstance(external, Mapping):
            raise SessionConflictError("live_start_review_revision_external_missing")
        final_path = Path(str(external["final_path"]))
        staging_path = Path(str(external["staging_path"]))
        inner_path = Path(str(external["inner_temp_path"]))
    if action == "materialize_review_revision_staging":
        source = pending["actions"][0]["materialization_source"]
        source_path = Path(str(source["path"]))
        payload = _read_plain_bytes(
            source_path,
            maximum_size=int(source["size"]),
        )
        if _sha256_bytes(payload) != source["sha256"]:
            raise SessionConflictError("live_start_review_revision_source_changed")
        published = atomic_write_reserved_bytes(
            path=staging_path,
            payload=payload,
            expected_parent_identity=tuple(external["parent_identity"]),
            expected_predecessor_identity=None,
            expected_predecessor_sha256=None,
            maximum_size=max(1, len(payload)),
        )
        evidence = {
            "staging_path": str(staging_path),
            "staging_parent_identity": list(path_identity(staging_path.parent)),
            "staging_identity": list(published.identity),
            "staging_size": len(payload),
            "staging_sha256": _sha256_bytes(payload),
        }
    elif action == "commit_bound_review_revision_request":
        staging_identity = tuple(external["staging_identity"])
        atomic_commit_bound_staging_no_replace(
            path=final_path,
            staging_path=staging_path,
            expected_staging_identity=staging_identity,
            expected_size=int(external["planned_successor_size"]),
            expected_sha256=str(external["planned_successor_sha256"]),
            expected_parent_identity=tuple(external["parent_identity"]),
        )
        evidence = {
            "final_path": str(final_path),
            "final_parent_identity": list(path_identity(final_path.parent)),
            "final_identity": list(path_identity(final_path)),
            "final_size": external["planned_successor_size"],
            "final_sha256": external["planned_successor_sha256"],
            "staging_absent": not path_lexists(staging_path),
        }
    elif action == "retire_candidate_validation_receipt":
        row = pending["actions"][0]
        receipt_path = Path(str(row["path"]))
        receipt_parent = receipt_path.parent
        receipt_present = path_lexists(receipt_path)
        directory_present = path_lexists(receipt_parent)
        if receipt_present:
            raw = _read_plain_bytes(
                receipt_path,
                maximum_size=int(row["historical_size"]),
            )
            if _sha256_bytes(raw) != row["historical_sha256"]:
                raise SessionConflictError("live_start_candidate_receipt_changed")
            secure_unlink(
                receipt_path,
                expected_identity=tuple(row["historical_identity"]),
                expected_parent_identity=tuple(row["parent_identity"]),
                missing_ok=False,
            )
        if directory_present:
            secure_rmdir_verified(
                receipt_parent,
                expected_identity=tuple(row["directory_identity"]),
                expected_parent_identity=tuple(row["directory_parent_identity"]),
            )
        evidence = {
            "path": row["path"],
            "parent_identity": row["parent_identity"],
            "historical_identity": row["historical_identity"],
            "historical_size": row["historical_size"],
            "historical_sha256": row["historical_sha256"],
            "directory_path": row["directory_path"],
            "directory_parent_identity": row["directory_parent_identity"],
            "directory_identity": row["directory_identity"],
            "disposition": "removed" if receipt_present else "already_absent",
            "directory_disposition": (
                "removed" if directory_present else "already_absent"
            ),
        }
    elif action == "restore_review_revision_predecessor":
        source = pending["actions"][0]["materialization_source"]
        evidence = {
            "source_path": source["path"],
            "source_parent_identity": source["parent_identity"],
            "historical_source_identity": source["identity"],
            "historical_source_size": source["size"],
            "historical_source_sha256": source["sha256"],
            "final_path": str(final_path),
            "staging_path": str(staging_path),
            "inner_temp_path": str(inner_path),
            "target_parent_identity": external["parent_identity"],
            "source_absent": True,
            "final_absent": True,
            "staging_absent": True,
            "inner_temp_absent": True,
        }
    elif action == "retire_unbound_review_revision_staging":
        for path in (staging_path, inner_path):
            if path_lexists(path):
                status = plain_file_status(path)
                secure_unlink(
                    path,
                    expected_identity=path_identity_from_status(status),
                    expected_parent_identity=path_identity(path.parent),
                    missing_ok=False,
                )
        evidence = {
            "final_path": str(final_path),
            "staging_path": str(staging_path),
            "inner_temp_path": str(inner_path),
            "parent_identity": external["parent_identity"],
            "final_absent": not path_lexists(final_path),
            "staging_absent": not path_lexists(staging_path),
            "inner_temp_absent": not path_lexists(inner_path),
        }
    else:
        raise SessionConflictError("live_start_review_revision_action_invalid")
    return _session.CandidateReviewRevisionPhysicalPostcondition(
        action=action,
        evidence=evidence,
    )


def _drive_candidate_review_revision(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
) -> LiveStartSession:
    while current.pending_transition is not None:
        authorization = _session.authorize_candidate_review_revision_under_lock(
            session_lease=session_lease,
            expected_revision_session=current,
        )
        action = authorization._opaque.action
        receipt = _session._execute_candidate_review_revision_physical_step(
            session_lease=session_lease,
            expected_revision_session=current,
            revision_authorization=authorization,
            action=action,
            physical_action=lambda: _review_revision_physical_step(
                current=current,
                action=action,
            ),
        )
        current = _session.advance_candidate_review_revision_under_lock(
            session_lease=session_lease,
            expected_revision_session=current,
            revision_step_receipt=receipt,
        )
    return current


def validate_live_start_review(
    *,
    session_root: Path,
    draft_path: Path,
) -> FrozenJsonDocument:
    """Install an independent approval or consume one shared revision."""

    with _session.lease_live_start_session(Path(session_root)) as session_lease:
        current = _session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        if current.terminal_status is not None:
            return _load_terminal_result(
                session_root=session_lease.session_root,
                terminal=current,
            ).summary
        if current.phase is not LiveStartPhase.CANDIDATE_VALIDATED:
            raise SessionConflictError("live_start_review_cursor_invalid")
        context = _load_bound_starter_context(
            session_root=session_lease.session_root
        )
        candidate = _load_bound_candidate(
            session_root=session_lease.session_root,
            context=context,
        )
        draft = _load_unsigned_draft(
            Path(draft_path),
            maximum_size=STARTER_REVIEW_MAX_BYTES,
        )
        try:
            version = context.document.to_value()["schema_version"]
            review_document = seal_starter_document(
                draft,
                expected_fields=QUALITY_STARTER_REVIEW_FIELDS
                if version == 3
                else STARTER_REVIEW_FIELDS,
                schema_version=version,
            )
            review = validate_starter_review(
                review_document,
                context=context,
                candidate=candidate,
                validation_receipt=_load_quality_candidate_receipt(
                    root=session_lease.session_root, current=current
                ),
            )
        except (TypeError, ValueError):
            return _terminalize_preapply_failure_under_lock(
                session_lease=session_lease, current=current, context=context,
                candidate=candidate, error_code="review_document_invalid",
            ).summary
        if review.review_status == "revision_requested":
            if current.revisions_used >= 2 or current.candidate_revision >= 3:
                return _terminalize_preapply_failure_under_lock(
                    session_lease=session_lease,
                    current=current,
                    context=context,
                    candidate=candidate,
                    error_code="revision_budget_exhausted",
                    incoming_review=review,
                ).summary
            source_path = _write_external_authority_source(
                session_root=session_lease.session_root,
                name=(
                    "review-revision-"
                    f"r{current.candidate_revision}-"
                    f"u{current.revisions_used}.json"
                ),
                payload=_session._canonical_json(review.document.to_value()),
            )
            current = _session.prepare_candidate_review_revision_under_lock(
                session_lease=session_lease,
                expected_validated_session=current,
                request_review_source_path=source_path,
            )
            current = _drive_candidate_review_revision(
                session_lease=session_lease,
                current=current,
            )
            return _review_revision_diagnostic(current=current, review=review)
        receipt = _session.seal_validation_receipt(
            receipt_kind="review_validation",
            unsigned_value={
                "run_id": current.run_id,
                "candidate_revision": current.candidate_revision,
                "starter_context_sha256": current.artifact_bindings[
                    "starter/starter_context.json"
                ],
                "candidate_sha256": current.artifact_bindings[
                    "starter/starter_config_candidate.json"
                ],
                "review_sha256": _sha256_bytes(review.document.canonical_json),
                "review_status": "approved",
                "confidence": review.confidence,
            },
        )
        current = _install_session_documents(
            session_lease=session_lease,
            current=current,
            operation="install_review_validation",
            final_event="review_approved",
            documents={
                "starter/starter_config_review.json": (
                    review.document.canonical_json
                ),
                "receipts/review_validation.json": (
                    FrozenJsonDocument.from_value(receipt).canonical_json + b"\n"
                ),
            },
        )
        del current
        return FrozenJsonDocument.from_value(receipt)


def _load_frozen_approval(
    *, session_root: Path, frozen: FrozenCompilerInputs
) -> ValidatedSingleStarterApproval:
    context = _load_bound_starter_context(session_root=session_root)
    candidate = _load_bound_candidate(session_root=session_root, context=context)
    version = context.document.to_value()["schema_version"]
    document = load_starter_document(
        session_root / "starter/starter_config_review.json",
        maximum_bytes=STARTER_REVIEW_MAX_BYTES,
        expected_fields=QUALITY_STARTER_REVIEW_FIELDS
        if version == 3
        else STARTER_REVIEW_FIELDS,
        schema_version=version,
    )
    receipt = _load_quality_candidate_receipt(root=session_root)
    review = validate_starter_review(
        document, context=context, candidate=candidate, validation_receipt=receipt
    )
    return ValidatedSingleStarterApproval(
        snapshot=frozen.manifest,
        context=context,
        candidate=candidate,
        review=review,
        validation_receipt=receipt,
    )


def _release_no_runtime_operation(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    profile_lease: OperatorProfileLease,
    operation_lease: OutputOperationAdmissionLease,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> LiveStartSession:
    binding = current.output_operation_admission_binding
    if not isinstance(binding, Mapping):
        return current
    if current.terminal_status is None or current.runtime_admission_binding is not None:
        raise SessionConflictError("live_start_no_runtime_terminal_required")
    if binding["state"] == "ACTIVE":
        successor = _session._thaw(binding)
        successor.pop("content_sha256")
        successor.update(
            state="TERMINAL_RELEASE_AUTHORIZED", release_handoff_kind="terminal_no_runtime"
        )
        current = _session._transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=current,
            event="same_phase_cas",
            changes={"output_operation_admission_binding": _session.seal_embedded_document(
                "output_operation_admission_binding", successor
            )},
        )
        invoke_live_start_fault(fault_hook, LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_RELEASE_AUTHORIZED)
    expected = load_bound_output_operation_admission(current)
    authorization = authorize_output_operation_terminal_release_from_context(
        operation_lease=operation_lease,
        session_lease=session_lease,
        expected_terminal_session=current,
        profile_lease=profile_lease,
        expected=expected,
    )
    _publisher.release_output_operation_admission_under_lease(
        operation_lease=operation_lease,
        session_lease=session_lease,
        expected_release_authorized_session=current,
        expected=expected,
        release_authorization=authorization,
        fault_hook=fault_hook,
    )
    return current


def _complete_no_runtime_result_under_lock(
    *, session_lease: LiveStartSessionLease, current: LiveStartSession,
    profile_lease: OperatorProfileLease, operation_lease: OutputOperationAdmissionLease,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    intent = current.result_intent
    if not isinstance(intent, Mapping) or intent["terminal_status"] != "PREVIEW_READY":
        return _session._complete_live_start_under_lock(
            session_lease=session_lease, expected_result_session=current,
            fault_hook=fault_hook,
        )
    publication = current.publication_binding
    if not isinstance(publication, Mapping):
        raise SessionConflictError("live_start_publication_binding_missing")
    root = Path(publication["output_child_path"])
    profile = profile_lease.profile
    with hold_plain_directory(profile.output_base_root, expected_identity=profile.output_base_root_identity) as base_guard:
        with hold_plain_directory(root, expected_identity=tuple(publication["output_child_identity"])) as output_guard:
            with ExclusiveFileLock(
                root / ".publish.lock", expected_parent_identity=output_guard.identity,
                path_guard=output_guard,
            ):
                def verify_publication() -> None:
                    base_guard.validate()
                    revalidate_operator_profile_lease(profile_lease)
                    observed = observe_output_operation_admission_under_lease(operation_lease)
                    binding = current.output_operation_admission_binding
                    if (
                        observed is None or not isinstance(binding, Mapping)
                        or binding["state"] != "ACTIVE"
                        or Path(binding["admission_path"]) != observed.admission_path
                        or tuple(binding["admission_parent_identity"]) != observed.admission_parent_identity
                        or tuple(binding["admission_identity"]) != observed.admission_identity
                        or binding["admission_size"] != observed.admission_size
                        or binding["admission_sha256"] != _publisher._admission_raw_sha256(observed)
                    ):
                        raise SessionConflictError("live_start_output_operation_binding_changed")
                    _require_exact_current_publication(current=current, output_guard=output_guard)

                verify_publication()
                return _session._complete_live_start_under_lock(
                    session_lease=session_lease, expected_result_session=current,
                    fault_hook=fault_hook, pre_terminal_check=verify_publication,
                )


def _terminal_release_already_complete(
    *, session_lease: LiveStartSessionLease, current: LiveStartSession,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> bool:
    if current.terminal_status is None:
        return False
    retirement = current.terminal_retirement
    if isinstance(retirement, Mapping) and retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED":
        admission, _result = _published_apply._load_release_authorized_runtime_context(
            session_lease=session_lease, cursor=current
        )
        authorization = _session.authorize_terminal_retirement_under_lock(
            session_lease=session_lease, expected_retirement_session=current
        )
        _published_apply._release_or_confirm_runtime_live_attempt_without_old_leases(
            session_lease=session_lease,
            expected_release_authorized_session=current,
            terminal_authorization=authorization,
            expected=admission,
            fault_hook=fault_hook,
        )
        return True
    if current.runtime_admission_binding is not None:
        return False
    binding = current.output_operation_admission_binding
    if binding is None:
        return True
    if binding["state"] != "TERMINAL_RELEASE_AUTHORIZED":
        return False
    with lease_output_operation_admission() as operation_lease:
        observed = observe_output_operation_admission_under_lease(operation_lease)
        if observed is None:
            return True
        if observed.admission_identity == tuple(binding["admission_identity"]):
            return False
        if observed.run_id == current.run_id or _publisher._admission_raw_sha256(observed) == binding["admission_sha256"]:
            raise SessionConflictError("live_start_output_operation_release_replaced_ambiguous")
        return True


def _complete_held_live_result(
    *,
    session_lease: LiveStartSessionLease,
    held: _published_apply.HeldApplyAndMatchPublished,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> LiveStartSession:
    current = held.updated_session
    if current.terminal_status is None:
        if current.result_intent is None:
            intent = _session._thaw(_published_apply._sealed_result_intent_from_held(
                session_lease=session_lease, held=held
            ))
            intent.pop("content_sha256")
            if current.schema_version == 2:
                intent["visible_limitations"] = list(_quality_available_limitations(
                    run_root=session_lease.session_root, current=current, progress={},
                ))
            else:
                context = _load_bound_starter_context(session_root=session_lease.session_root)
                intent["visible_limitations"] = list(_starter_context_limitations(context.document.to_value()))
                if intent["review_confidence"] == "limited" and not intent["visible_limitations"]:
                    intent["visible_limitations"] = ["Independent reviewer confidence is limited."]
            evidence = held.acknowledgement_evidence
            acknowledgement = (
                None if evidence is None else _published_apply._sealed_attempt_acknowledgement(
                    run_id=current.run_id, evidence=evidence
                )
            )
            current = _session.bind_result_intent_under_lock(
                session_lease=session_lease,
                expected_session=current,
                result_intent=_session.seal_embedded_document("result_intent", intent),
                attempt_acknowledgement=acknowledgement,
            )
            invoke_live_start_fault(fault_hook, LiveStartFaultPoint.AFTER_RESULT_INTENT)
            if acknowledgement is not None:
                invoke_live_start_fault(fault_hook, LiveStartFaultPoint.AFTER_ACKNOWLEDGEMENT_INTENT)
        current = _session._complete_live_start_under_lock(
            session_lease=session_lease, expected_result_session=current,
            fault_hook=fault_hook,
        )
    retirement = current.terminal_retirement
    operation = (
        retirement["operation"] if isinstance(retirement, Mapping)
        else _published_apply._stable_terminal_operation_without_retirement(current)
    )
    if operation == "ack_success":
        return held.acknowledge_after_terminal(
            session_lease=session_lease, expected_terminal_session=current
        )
    if operation == "release_not_committed":
        return held.release_admission_after_terminal(
            session_lease=session_lease, expected_terminal_session=current
        )
    if operation == "release_committed_mismatch" or (
        _published_apply._is_terminal_resolution_recovery(current)
        and held.result.physical_disposition is _published_apply.PhysicalApplyDisposition.NOT_COMMITTED
    ):
        return held.resolve_and_release_after_terminal(
            session_lease=session_lease, expected_terminal_session=current
        )
    return current


def _resume_starter_intake_under_lock(
    *, session_lease: LiveStartSessionLease, current: LiveStartSession,
    frozen: FrozenCompilerInputs,
) -> tuple[LiveStartSession, FrozenJsonDocument | None]:
    pending = current.pending_transition
    if isinstance(pending, Mapping):
        operation = pending["operation"]
        if operation == "review_revision":
            current = _drive_candidate_review_revision(session_lease=session_lease, current=current)
        elif operation in {"install_candidate", "install_candidate_validation", "install_review_validation"}:
            event = {
                "install_candidate": (
                    "initial_draft" if current.phase is LiveStartPhase.INPUT_FROZEN else "replacement_draft"
                ),
                "install_candidate_validation": "candidate_valid",
                "install_review_validation": "review_approved",
            }[operation]
            current = _continue_pending_document_install(
                session_lease=session_lease, current=current, final_event=event
            )
    if current.phase not in {
        LiveStartPhase.INPUT_FROZEN, LiveStartPhase.CANDIDATE_DRAFTED,
        LiveStartPhase.CANDIDATE_VALIDATED,
    }:
        return current, None
    context = (
        build_quality_starter_context(frozen)
        if current.schema_version == 2
        else build_single_candidate_starter_context(frozen)
    )
    if (current.phase is LiveStartPhase.CANDIDATE_DRAFTED
        and current.pending_transition is None
        and current.revisions_used == current.candidate_revision):
        if "starter/starter_config_review.json" in current.artifact_bindings:
            bound_context = _load_bound_starter_context(session_root=session_lease.session_root)
            review = _load_bound_revision_review(
                session_root=session_lease.session_root, current=current, context=bound_context,
            )
            return current, _review_revision_diagnostic(current=current, review=review)
        finding = _candidate_validation_finding(session_root=session_lease.session_root)
        if finding is None:
            from hsconfig.starter_candidate import historical_mulligan_conflict_finding

            bound_context = _load_bound_starter_context(session_root=session_lease.session_root)
            finding = historical_mulligan_conflict_finding(_load_bound_candidate(
                session_root=session_lease.session_root, context=bound_context,
            ))
        if finding is None:
            raise SessionConflictError("live_start_rejected_candidate_now_valid")
        return current, _candidate_revision_diagnostic(current=current, finding=finding)
    if (current.phase is LiveStartPhase.CANDIDATE_DRAFTED
        and current.revisions_used < current.candidate_revision):
        current, validation = _validate_installed_candidate_under_lock(
            session_lease=session_lease, current=current, context=context
        )
        if current.terminal_status is not None:
            return current, None
        if current.phase is LiveStartPhase.CANDIDATE_DRAFTED:
            return current, validation
    context_path = _materialize_starter_context(
        local_app_data_root=session_lease.session_root.parent.parent.parent,
        run_id=current.run_id, payload=context.document.canonical_json,
    )
    needs_review = current.phase is LiveStartPhase.CANDIDATE_VALIDATED
    return current, _sealed_diagnostic({
        "schema_version": 1,
        "diagnostic_kind": "live_start_resume",
        "status": "awaiting_review" if needs_review else "awaiting_candidate",
        "run_root": str(session_lease.session_root),
        "phase": current.phase.value,
        "context_path": str(context_path),
        "candidate_revision": current.candidate_revision,
        "next_candidate_revision": current.candidate_revision + int(
            current.phase is LiveStartPhase.CANDIDATE_DRAFTED
            and current.revisions_used == current.candidate_revision
        ),
        "revisions_used": current.revisions_used,
        "findings": [],
    })


def _continue_live_start_under_lock(
    *, session_lease: LiveStartSessionLease, current: LiveStartSession,
    fault_hook: LiveStartFaultHook, resume_intake: bool,
) -> LiveStartResult | FrozenJsonDocument:
    root = session_lease.session_root
    if _terminal_release_already_complete(
        session_lease=session_lease, current=current, fault_hook=fault_hook
    ):
        return _load_terminal_result(session_root=root, terminal=current)
    profile = load_operator_profile()
    with lease_operator_profile(expected_profile=profile) as profile_lease:
        frozen = _load_frozen_compiler_inputs(root, rebind_operator=False)
        operator = frozen.manifest.operator_bindings.to_value()
        compiler = frozen.manifest.compiler_inputs.to_value()
        _persisted_live_document_version(root)
        if (
            profile.content_sha256 != operator["operator_profile_sha256"]
            or profile.runtime_root != Path(operator["runtime_root"])
            or profile.runtime_root_identity != tuple(operator["runtime_root_identity"])
            or profile.output_base_root != Path(operator["output_base_root"])
            or profile.output_base_root_identity != tuple(operator["output_base_root_identity"])
        ):
            raise SessionConflictError("live_start_operator_profile_changed")
        current = _session.validate_resume_under_lock(
            session_lease=session_lease,
            expected_deck_code_sha256=compiler["deck_code_sha256"],
            expected_input_snapshot_manifest_sha256=frozen.manifest.document.content_sha256,
            expected_runtime_grammar_version=_RUNTIME_GRAMMAR_VERSION,
            expected_compiler_contract_id="hsconfig-live-start-v2"
            if current.schema_version == 2
            else _COMPILER_CONTRACT_ID,
        )
        if not profile.live_by_default and not current.preview_requested:
            raise SessionConflictError("live_start_operator_profile_live_disabled")
        if resume_intake:
            current, progress = _resume_starter_intake_under_lock(
                session_lease=session_lease, current=current, frozen=frozen
            )
            if progress is not None:
                return progress
        with lease_output_operation_admission() as operation_lease:
            pending = current.pending_transition
            if (isinstance(pending, Mapping)
                and pending["operation"] == "install_apply_invocation"
                and pending["stage"] == "PREPARED"):
                current = _published_apply._recover_prepared_apply_not_started_under_lock(
                    session_lease=session_lease, expected_session=current,
                    profile_lease=profile_lease, output_operation_lease=operation_lease,
                )
                pending = current.pending_transition
            recovery_only = (
                current.apply_invocation_sha256 is not None
                or current.apply_recovery is not None
                or isinstance(pending, Mapping) and pending["operation"] == "install_apply_invocation"
            )
            if recovery_only:
                with _published_apply._recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    output_operation_lease=operation_lease,
                    expected_session=current,
                    fault_hook=fault_hook,
                ) as recovered:
                    current = _complete_held_live_result(
                        session_lease=session_lease, held=recovered.held, fault_hook=fault_hook
                    )
            elif current.terminal_status is not None:
                current = _release_no_runtime_operation(
                    session_lease=session_lease, current=current,
                    profile_lease=profile_lease, operation_lease=operation_lease,
                    fault_hook=fault_hook,
                )
            elif current.result_intent is not None:
                current = _complete_no_runtime_result_under_lock(
                    session_lease=session_lease, current=current, profile_lease=profile_lease,
                    operation_lease=operation_lease,
                    fault_hook=fault_hook,
                )
                current = _release_no_runtime_operation(
                    session_lease=session_lease, current=current,
                    profile_lease=profile_lease, operation_lease=operation_lease,
                    fault_hook=fault_hook,
                )
            else:
                if current.phase not in {
                    LiveStartPhase.REVIEW_APPROVED,
                    LiveStartPhase.PACKAGE_VALIDATED,
                    LiveStartPhase.PREPUBLICATION_CHECK_PASSED,
                    LiveStartPhase.PUBLICATION_COMMITTED,
                }:
                    raise SessionConflictError("live_start_review_approval_required")
                approval = _load_frozen_approval(session_root=root, frozen=frozen)
                request = FrozenApprovedLiveConfigureRequest.from_values(
                    frozen_compiler_inputs=frozen, starter_approval=approval
                )
                run_model = build_frozen_live_configure_run(request=request)
                current = _drive_live_start_pipeline(
                    run_model=run_model,
                    session_lease=session_lease,
                    expected_session=current,
                    runtime_root=profile.runtime_root,
                    profile_lease=profile_lease,
                    operation_lease=operation_lease,
                    fault_hook=fault_hook,
                )
                if current.preview_requested:
                    if current.result_intent is None:
                        intent = _session._thaw(_failure_result_intent(
                            current=current, context=approval.context,
                            candidate=approval.candidate, error_code="preview",
                        ))
                        intent.pop("content_sha256")
                        intent.update(
                            terminal_status="PREVIEW_READY",
                            review_confidence=approval.review.confidence,
                            visible_limitations=list(_starter_context_limitations(
                                approval.context.document.to_value(), review=approval.review,
                            )),
                            error_code=None,
                            retained_safe_state="PUBLISHED_PREVIEW_RUNTIME_UNCHANGED",
                        )
                        current = _session._transition_receipt_authorized_under_lock(
                            session_lease=session_lease, expected_session=current,
                            event="same_phase_cas", changes={"result_intent":
                                _session.seal_embedded_document("result_intent", intent)},
                        )
                        invoke_live_start_fault(fault_hook, LiveStartFaultPoint.AFTER_RESULT_INTENT)
                    current = _complete_no_runtime_result_under_lock(
                        session_lease=session_lease, current=current, profile_lease=profile_lease,
                        operation_lease=operation_lease,
                        fault_hook=fault_hook,
                    )
                    current = _release_no_runtime_operation(
                        session_lease=session_lease, current=current,
                        profile_lease=profile_lease, operation_lease=operation_lease,
                        fault_hook=fault_hook,
                    )
                else:
                    publication = current.publication_binding
                    if not isinstance(publication, Mapping):
                        raise SessionConflictError("live_start_publication_missing")
                    with _published_apply._apply_and_match_published(
                        session_lease=session_lease,
                        expected_session=current,
                        profile_lease=profile_lease,
                        output_operation_lease=operation_lease,
                        output_operation_admission=load_bound_output_operation_admission(current),
                        output_root=Path(publication["output_child_path"]),
                        publication_content_root_sha256=publication["content_root_sha256"],
                        runtime_root=profile.runtime_root,
                        apply_attempt_id=secrets.token_hex(16),
                        fault_hook=fault_hook,
                    ) as held:
                        current = _complete_held_live_result(
                            session_lease=session_lease, held=held, fault_hook=fault_hook
                        )
    return _load_terminal_result(session_root=root, terminal=current)


def finalize_live_start(*, session_root: Path) -> LiveStartResult:
    """Complete the approved frozen run under one uninterrupted session lease."""

    result = _finalize_live_start(session_root=session_root, fault_hook=no_live_start_fault)
    if not isinstance(result, LiveStartResult):
        raise SessionConflictError("live_start_review_approval_required")
    return result


def _finalize_live_start(
    *, session_root: Path, fault_hook: LiveStartFaultHook,
    resume_intake: bool = False,
) -> LiveStartResult | FrozenJsonDocument:
    with _session.lease_live_start_session(Path(session_root)) as session_lease:
        current = _session.load_live_start_session_under_lock(session_lease=session_lease)
        if current.phase is LiveStartPhase.DISCOVERY_REQUIRED:
            if not resume_intake:
                raise SessionConflictError("live_start_quality_discovery_required")
            return _quality_research_under_lock(
                session_lease=session_lease, current=current
            )
        return _continue_live_start_under_lock(
            session_lease=session_lease, current=current,
            fault_hook=fault_hook, resume_intake=resume_intake,
        )


def resume_live_start(
    *, session_root: Path
) -> LiveStartResult | FrozenJsonDocument | LiveStartDiscovery | LiveStartPreparation:
    """Resume only the explicitly named run; an admitted apply is recovery-only."""

    return _finalize_live_start(
        session_root=session_root, fault_hook=no_live_start_fault, resume_intake=True
    )


__all__ = (
    "LiveStartDiscovery",
    "LiveStartPreparation",
    "LiveStartRequest",
    "LiveStartResult",
    "ValidatedPrepublication",
    "build_frozen_live_configure_run",
    "lease_validated_prepublication",
    "prepare_live_start",
    "prepare_quality_live_start",
    "complete_live_start_research",
    "quality_start_summary",
    "validate_live_start_candidate",
    "validate_live_start_review",
    "finalize_live_start",
    "resume_live_start",
    "publish_validated_prepublication",
)
