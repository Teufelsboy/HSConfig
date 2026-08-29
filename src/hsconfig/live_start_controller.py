"""Frozen-authority live-start prepublication and guarded publication seams."""

from __future__ import annotations

import json
import stat
from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from hsconfig import live_start_session as _session
from hsconfig import output_publisher as _publisher
from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.atomic_io import (
    AtomicWriteConflictError,
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
    OperatorProfileLease,
    revalidate_operator_profile_lease,
)
from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import load_operator_summary_inputs
from hsconfig.output_operation_admission import (
    OutputOperationAdmissionEvidence,
    OutputOperationAdmissionLease,
    build_output_operation_admission_bytes,
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
    secure_replace,
    secure_rmdir_verified,
    secure_unlink,
    secure_unlink_verified,
    snapshot_bounded_filesystem_package,
    status_is_reparse,
)
from hsconfig.package_request import FrozenJsonDocument, ResolvedPackageRequest
from hsconfig.runtime_apply import plan_apply_package
from hsconfig.strict_package_validation import (
    strict_validation_passed,
    validate_complete_configure_run_from_view,
)


_PACKAGE_RECEIPT_LOGICAL = "receipts/package_validation.json"
_PREPUBLICATION_RECEIPT_LOGICAL = "receipts/prepublication_apply_check.json"
_MAX_RECEIPT_BYTES = 256 * 1024


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
    *, request: ResolvedPackageRequest
) -> ConfigureRunModel:
    """Compile one run solely from the request's sealed frozen authority."""

    if not isinstance(request, ResolvedPackageRequest):
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
                    assert isinstance(pending, Mapping)
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
    gate = evaluate_apply_gate(package_root)
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
) -> tuple[LiveStartSession, FrozenJsonDocument]:
    planned = plan_apply_package(
        package_root=package_root,
        runtime_root=runtime_root,
    )
    planned["created_at_utc"] = f"{bound_date}T00:00:00+00:00"
    planned["diagnostic_only"] = True
    planned["package_root"] = str(package_root.resolve())
    planned["package_root_sha256"] = package_root_sha256
    document = FrozenJsonDocument.from_value(planned)
    _emit_pipeline_event("fake_apply_planned")
    if current.phase is LiveStartPhase.PACKAGE_VALIDATED:
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
        _require_exact_receipt(
            session_lease.session_root / _PREPUBLICATION_RECEIPT_LOGICAL,
            document.canonical_json,
        )
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
        observed != expected
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
    assert isinstance(child, Mapping)
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
    if current.output_operation_admission_binding is None and pending is None:
        if observe_output_operation_admission_under_lease(operation_lease) is not None:
            raise ValueError("live_start_output_operation_already_present")
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
    cleanup_parent, observed_cleanup_parent_identity = _cleanup_parent(
        session_lease,
        operation_lease=operation_lease,
        create_if_missing=pending is None,
    )
    if pending is None:
        work_binding = current.prepublication_work_binding
        cleanup_parent_identity = observed_cleanup_parent_identity
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
        assert isinstance(work, Mapping)
        _require_cleanup_work_root_present(
            work_parent_guard=work_parent_guard,
            work_root=Path(str(work["work_root"])),
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
        assert isinstance(work, Mapping)
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
        assert inventory is not None
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
        assert isinstance(pending, Mapping)
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
        changes={"pending_transition": None},
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


__all__ = (
    "ValidatedPrepublication",
    "build_frozen_live_configure_run",
    "lease_validated_prepublication",
    "publish_validated_prepublication",
)
