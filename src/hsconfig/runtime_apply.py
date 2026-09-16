from __future__ import annotations

import json
import re
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, get_ident
from typing import TYPE_CHECKING, Any, Iterator, Literal

if TYPE_CHECKING:
    from hsconfig.input_snapshot_manifest import FrozenCompilerInputs

from hsconfig.apply_invocation import (
    ApplyInvocation,
    capture_pre_apply_runtime_snapshot,
    require_same_attempt_pre_apply_snapshot,
)
from hsconfig.atomic_io import FaultHook, no_fault
from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.current_output import (
    PackageInputLease,
    lease_package_input,
    revalidate_package_input_lease,
)
from hsconfig.live_start_faults import (
    LiveStartFaultHook,
    LiveStartFaultPoint,
    invoke_live_start_fault,
    no_live_start_fault,
)
from hsconfig.output_operation_admission import (
    OutputOperationAdmissionLease,
    lease_output_operation_admission,
    require_output_operation_allows_runtime_mutation,
)
from hsconfig.output_publisher import (
    PublishedOutput,
    _bootstrap_neutral_output_locks,
)
from hsconfig.runtime_apply_receipts import (
    build_fake_apply_receipt,
    verify_fake_apply_receipt,
)
from hsconfig.package_io import (
    FilesystemPathGuard,
    PathIdentity,
    capture_plain_ancestor_guard,
    path_identity,
    path_lexists,
    require_plain_directory,
    require_same_identity_resolution,
    secure_create_directory,
)
from hsconfig.runtime_installer import (
    ControllerApplyLeasePair,
    RuntimeInstallPlan,
    RuntimeInstallResult,
    _install_runtime_package_under_output_operation,
    _require_active_controller_apply_pair,
    _state_key,
    install_runtime_package as _install_runtime_package,
    observe_runtime_layout_bootstrap_from_pair,
    plan_runtime_install,
)
from hsconfig.live_start_session import (
    RuntimeLayoutBootstrapEvidence,
    load_live_start_session_under_lock,
)
from hsconfig.runtime_live_admission import RuntimeLiveAttemptAdmissionEvidence
from hsconfig.runtime_live_admission import (
    require_live_admission_allows_legacy_root_bootstrap,
)
from hsconfig.strict_package_validation import (
    LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
    LINKED_RUNTIME_OWNER_EVIDENCE_MISSING,
    strict_validation_passed,
    validate_complete_package,
)


_REVISION_NAME = re.compile(r"sha256-[0-9a-f]{64}")
_LEGACY_ROOT_BOOTSTRAP_AUTHORITY = object()


@dataclass(frozen=True, slots=True)
class _OutputOperationInstallContext:
    operation_lease: OutputOperationAdmissionLease
    package_lease: PackageInputLease
    expected_root_identity: PathIdentity


_ACTIVE_OUTPUT_OPERATION_INSTALL: ContextVar[
    _OutputOperationInstallContext | None
] = ContextVar("hsconfig_active_output_operation_install", default=None)

# Read-only authority-boundary tests still monkeypatch this removed private
# boundary to prove validation fails before any legacy destination work.  The
# sentinel is intentionally non-callable; no backup implementation remains.
_snapshot_existing_runtime_target: None = None


@dataclass(frozen=True, slots=True, init=False)
class _LegacyRuntimeRootBootstrapAuthorization:
    """Opaque one-shot authority for the compatibility-only root bootstrap."""

    _nonce: object
    _thread_id: int

    def __init__(self, authority: object | None = None) -> None:
        if authority is not _LEGACY_ROOT_BOOTSTRAP_AUTHORITY:
            raise TypeError(
                "legacy_runtime_root_bootstrap_authorization_not_constructible"
            )
        object.__setattr__(self, "_nonce", object())
        object.__setattr__(self, "_thread_id", get_ident())

    def __copy__(self) -> _LegacyRuntimeRootBootstrapAuthorization:
        raise TypeError(
            "legacy_runtime_root_bootstrap_authorization_not_copyable"
        )

    def __deepcopy__(
        self,
        memo: dict[int, object],
    ) -> _LegacyRuntimeRootBootstrapAuthorization:
        del memo
        raise TypeError(
            "legacy_runtime_root_bootstrap_authorization_not_copyable"
        )

    def __reduce__(self) -> object:
        raise TypeError(
            "legacy_runtime_root_bootstrap_authorization_not_serializable"
        )


@dataclass(frozen=True, slots=True)
class LegacyRuntimeRootBootstrapEvidence:
    runtime_root: Path
    predecessor_state: Literal["absent", "existing"]
    predecessor_identity: PathIdentity | None
    successor_identity: PathIdentity
    bound_ancestor_path: Path
    bound_ancestor_identity: PathIdentity
    created_directory_identities: tuple[PathIdentity, ...]


@dataclass(frozen=True, slots=True)
class PreparedPackageInstall:
    plan: RuntimeInstallPlan
    runtime_layout_evidence: RuntimeLayoutBootstrapEvidence
    apply_gate: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _LegacyRuntimeRootBootstrapBinding:
    authorization: _LegacyRuntimeRootBootstrapAuthorization
    thread_id: int
    output_operation_lease: OutputOperationAdmissionLease
    package_lease: PackageInputLease
    runtime_root: Path
    expected_predecessor_identity: PathIdentity | None
    bound_ancestor_path: Path
    bound_ancestor_identity: PathIdentity
    ancestor_guard: FilesystemPathGuard
    config_dir: str
    apply_gate: dict[str, Any]
    apply_gate_canonical: bytes
    fake_apply_receipt: dict[str, Any]
    fake_apply_receipt_canonical: bytes


_active_legacy_root_bootstraps: dict[
    int,
    _LegacyRuntimeRootBootstrapBinding,
] = {}
_active_legacy_root_bootstraps_lock = Lock()


def _canonical_json_mapping(value: dict[str, Any], *, field: str) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError(f"{field}_invalid") from error


def _require_bound_runtime_ancestor(
    *,
    runtime_root: Path,
    bound_ancestor_path: Path,
    bound_ancestor_identity: PathIdentity,
) -> tuple[Path, Path, FilesystemPathGuard]:
    root = Path(runtime_root).absolute()
    ancestor = Path(bound_ancestor_path).absolute()
    if root != Path(runtime_root) or ancestor != Path(bound_ancestor_path):
        raise ValueError("legacy_runtime_root_path_not_canonical")
    try:
        relative = root.relative_to(ancestor)
    except ValueError as error:
        raise ValueError("legacy_runtime_root_ancestor_invalid") from error
    if not relative.parts:
        return root, ancestor, capture_plain_ancestor_guard(root)
    require_plain_directory(ancestor)
    require_same_identity_resolution(ancestor)
    if path_identity(ancestor) != tuple(bound_ancestor_identity):
        raise ValueError("legacy_runtime_root_ancestor_changed")
    guard = capture_plain_ancestor_guard(root)
    guard.validate()
    return root, ancestor, guard


def _authorize_legacy_runtime_root_bootstrap_from_context(
    *,
    output_operation_lease: OutputOperationAdmissionLease,
    package_lease: PackageInputLease,
    runtime_root: Path,
    expected_predecessor_identity: PathIdentity | None,
    bound_ancestor_path: Path,
    bound_ancestor_identity: PathIdentity,
    config_dir: str,
    apply_gate: dict[str, Any],
    fake_apply_receipt: dict[str, Any],
) -> _LegacyRuntimeRootBootstrapAuthorization:
    """Mint one root-bootstrap authority only after every public writer gate."""

    if not isinstance(output_operation_lease, OutputOperationAdmissionLease):
        raise ValueError("legacy_runtime_root_output_operation_lease_invalid")
    if not isinstance(package_lease, PackageInputLease):
        raise ValueError("legacy_runtime_root_package_lease_invalid")
    if not isinstance(apply_gate, dict) or not isinstance(
        fake_apply_receipt,
        dict,
    ):
        raise ValueError("legacy_runtime_root_apply_authority_invalid")
    _validate_config_dir(config_dir)
    root, ancestor, guard = _require_bound_runtime_ancestor(
        runtime_root=runtime_root,
        bound_ancestor_path=bound_ancestor_path,
        bound_ancestor_identity=bound_ancestor_identity,
    )
    predecessor_identity = (
        None
        if expected_predecessor_identity is None
        else tuple(expected_predecessor_identity)
    )
    if predecessor_identity is None:
        if path_lexists(root):
            raise ValueError("legacy_runtime_root_predecessor_changed")
    else:
        require_plain_directory(root)
        require_same_identity_resolution(root)
        if path_identity(root) != predecessor_identity:
            raise ValueError("legacy_runtime_root_predecessor_changed")

    require_output_operation_allows_runtime_mutation(
        lease=output_operation_lease
    )
    revalidate_package_input_lease(package_lease)
    resolved_gate = _resolve_allowed_apply_gate(
        package=package_lease.package_root,
        apply_gate=apply_gate,
        allow_source_informed=False,
    )
    if resolved_gate != apply_gate:
        raise ValueError("legacy_runtime_root_apply_gate_changed")
    verify_fake_apply_receipt(
        package_root=package_lease.package_root,
        runtime_root=root,
        config_dir=config_dir,
        receipt=fake_apply_receipt,
    )
    require_live_admission_allows_legacy_root_bootstrap(
        runtime_root=root
    )

    authorization = _LegacyRuntimeRootBootstrapAuthorization(
        _LEGACY_ROOT_BOOTSTRAP_AUTHORITY
    )
    binding = _LegacyRuntimeRootBootstrapBinding(
        authorization=authorization,
        thread_id=get_ident(),
        output_operation_lease=output_operation_lease,
        package_lease=package_lease,
        runtime_root=root,
        expected_predecessor_identity=predecessor_identity,
        bound_ancestor_path=ancestor,
        bound_ancestor_identity=tuple(bound_ancestor_identity),
        ancestor_guard=guard,
        config_dir=config_dir,
        apply_gate=apply_gate,
        apply_gate_canonical=_canonical_json_mapping(
            apply_gate,
            field="legacy_runtime_root_apply_gate",
        ),
        fake_apply_receipt=fake_apply_receipt,
        fake_apply_receipt_canonical=_canonical_json_mapping(
            fake_apply_receipt,
            field="legacy_runtime_root_fake_receipt",
        ),
    )
    with _active_legacy_root_bootstraps_lock:
        if id(authorization) in _active_legacy_root_bootstraps:
            raise ValueError("legacy_runtime_root_bootstrap_token_collision")
        _active_legacy_root_bootstraps[id(authorization)] = binding
    return authorization


def _consume_legacy_runtime_root_bootstrap_authorization(
    authorization: _LegacyRuntimeRootBootstrapAuthorization,
) -> _LegacyRuntimeRootBootstrapBinding:
    if not isinstance(
        authorization,
        _LegacyRuntimeRootBootstrapAuthorization,
    ):
        raise ValueError("legacy_runtime_root_bootstrap_authorization_invalid")
    with _active_legacy_root_bootstraps_lock:
        binding = _active_legacy_root_bootstraps.get(id(authorization))
        if (
            binding is None
            or binding.authorization is not authorization
            or authorization._thread_id != binding.thread_id
            or binding.thread_id != get_ident()
        ):
            raise ValueError(
                "legacy_runtime_root_bootstrap_authorization_inactive_or_forged"
            )
        del _active_legacy_root_bootstraps[id(authorization)]
    return binding


def _bootstrap_legacy_runtime_root_from_context(
    *,
    authorization: _LegacyRuntimeRootBootstrapAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> LegacyRuntimeRootBootstrapEvidence:
    """Consume one authority and create only its identity-bound directory chain."""

    binding = _consume_legacy_runtime_root_bootstrap_authorization(
        authorization
    )
    if (
        _canonical_json_mapping(
            binding.apply_gate,
            field="legacy_runtime_root_apply_gate",
        )
        != binding.apply_gate_canonical
        or _canonical_json_mapping(
            binding.fake_apply_receipt,
            field="legacy_runtime_root_fake_receipt",
        )
        != binding.fake_apply_receipt_canonical
    ):
        raise ValueError("legacy_runtime_root_bootstrap_authority_changed")

    require_output_operation_allows_runtime_mutation(
        lease=binding.output_operation_lease
    )
    revalidate_package_input_lease(binding.package_lease)
    resolved_gate = _resolve_allowed_apply_gate(
        package=binding.package_lease.package_root,
        apply_gate=binding.apply_gate,
        allow_source_informed=False,
    )
    if resolved_gate != binding.apply_gate:
        raise ValueError("legacy_runtime_root_apply_gate_changed")
    verify_fake_apply_receipt(
        package_root=binding.package_lease.package_root,
        runtime_root=binding.runtime_root,
        config_dir=binding.config_dir,
        receipt=binding.fake_apply_receipt,
    )
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.AFTER_AUTHORIZATION_CONSUMED_BEFORE_PHYSICAL_CALLBACK,
    )
    binding.ancestor_guard.validate()
    if (
        path_identity(binding.bound_ancestor_path)
        != binding.bound_ancestor_identity
    ):
        raise ValueError("legacy_runtime_root_ancestor_changed")

    # This is deliberately the final gate before the first Runtime-path
    # observation or creation callback. The fault boundary and ancestor checks
    # run first so a newly published admission cannot slip between this check
    # and the Runtime-root branch or mkdir.
    require_live_admission_allows_legacy_root_bootstrap(
        runtime_root=binding.runtime_root
    )

    if binding.expected_predecessor_identity is not None:
        require_plain_directory(binding.runtime_root)
        require_same_identity_resolution(binding.runtime_root)
        successor = path_identity(binding.runtime_root)
        if successor != binding.expected_predecessor_identity:
            raise ValueError("legacy_runtime_root_predecessor_changed")
        return LegacyRuntimeRootBootstrapEvidence(
            runtime_root=binding.runtime_root,
            predecessor_state="existing",
            predecessor_identity=binding.expected_predecessor_identity,
            successor_identity=successor,
            bound_ancestor_path=binding.bound_ancestor_path,
            bound_ancestor_identity=binding.bound_ancestor_identity,
            created_directory_identities=(),
        )

    if path_lexists(binding.runtime_root):
        raise ValueError("legacy_runtime_root_predecessor_changed")
    relative = binding.runtime_root.relative_to(binding.bound_ancestor_path)
    current = binding.bound_ancestor_path
    parent_identity = binding.bound_ancestor_identity
    created: list[PathIdentity] = []
    for component in relative.parts:
        child = current / component
        if path_lexists(child):
            raise ValueError("legacy_runtime_root_predecessor_changed")
        try:
            child_identity = secure_create_directory(
                child,
                expected_parent_identity=parent_identity,
            )
        except FileExistsError as error:
            raise ValueError(
                "legacy_runtime_root_predecessor_changed"
            ) from error
        require_plain_directory(child)
        require_same_identity_resolution(child)
        if path_identity(child) != child_identity:
            raise ValueError("legacy_runtime_root_successor_changed")
        created.append(child_identity)
        current = child
        parent_identity = child_identity
        binding.ancestor_guard.validate()

    if current != binding.runtime_root or not created:
        raise ValueError("legacy_runtime_root_bootstrap_incomplete")
    successor = path_identity(binding.runtime_root)
    if successor != created[-1]:
        raise ValueError("legacy_runtime_root_successor_changed")
    return LegacyRuntimeRootBootstrapEvidence(
        runtime_root=binding.runtime_root,
        predecessor_state="absent",
        predecessor_identity=None,
        successor_identity=successor,
        bound_ancestor_path=binding.bound_ancestor_path,
        bound_ancestor_identity=binding.bound_ancestor_identity,
        created_directory_identities=tuple(created),
    )


def _nearest_existing_runtime_ancestor(path: Path) -> tuple[Path, PathIdentity]:
    candidate = Path(path).absolute()
    current = candidate
    while not path_lexists(current):
        parent = current.parent
        if parent == current:
            raise ValueError("legacy_runtime_root_ancestor_missing")
        current = parent
    require_plain_directory(current)
    require_same_identity_resolution(current)
    return current, path_identity(current)


def prepare_package_install_from_lease(
    *,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    apply_gate: dict[str, Any] | None = None,
    runtime_layout_evidence: RuntimeLayoutBootstrapEvidence | None = None,
) -> PreparedPackageInstall:
    """Plan one install from the already-held publication/runtime pair."""

    binding = _require_active_controller_apply_pair(lease_pair)
    if (
        not isinstance(invocation, ApplyInvocation)
        or type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence
        or binding.runtime_admission is not runtime_admission
        or invocation.apply_attempt_id != runtime_admission.apply_attempt_id
        or invocation.run_id != runtime_admission.run_id
        or invocation.content_sha256
        != runtime_admission.apply_invocation_sha256
        or invocation.runtime_root != lease_pair.runtime_lease.runtime_root
        or invocation.runtime_root_identity
        != lease_pair.runtime_lease.runtime_root_identity
        or invocation.pre_apply_runtime_snapshot.content_sha256
        != runtime_admission.pre_apply_runtime_snapshot_sha256
    ):
        raise ValueError("prepared_package_install_context_invalid")
    package_lease = lease_pair.package_lease
    revalidate_package_input_lease(package_lease)
    package = package_lease.package_root
    _validate_runtime_apply_package(package)
    resolved_gate = _resolve_allowed_apply_gate(
        package=package,
        apply_gate=apply_gate,
        allow_source_informed=False,
    )
    current_snapshot = capture_pre_apply_runtime_snapshot(
        runtime_root=invocation.runtime_root,
        expected_runtime_root_identity=invocation.runtime_root_identity,
        deck_name=invocation.pre_apply_runtime_snapshot.deck_name,
        state_key=_state_key(invocation.pre_apply_runtime_snapshot.deck_name),
        profile_lease=binding.profile_lease,
    )
    require_same_attempt_pre_apply_snapshot(
        sealed=invocation.pre_apply_runtime_snapshot,
        current=current_snapshot,
        apply_attempt_id=invocation.apply_attempt_id,
        validated_delta=None,
    )
    published = _published_output(package_lease)
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=invocation.runtime_root,
    )
    logical_config_dir = _logical_config_dir(package, None)
    if plan.logical_config_dir != logical_config_dir:
        raise ValueError("config_dir_mismatch")
    if runtime_layout_evidence is None:
        layout = observe_runtime_layout_bootstrap_from_pair(
            lease_pair=lease_pair,
            transaction_id=invocation.apply_attempt_id,
            retention_owner_run_id=invocation.run_id,
            runtime_admission=runtime_admission,
            state_key=_state_key(invocation.pre_apply_runtime_snapshot.deck_name),
        )
    else:
        if type(runtime_layout_evidence) is not RuntimeLayoutBootstrapEvidence:
            raise TypeError("prepared_package_install_layout_invalid")
        persisted = load_live_start_session_under_lock(
            session_lease=binding.session_lease
        )
        layout_value = runtime_layout_evidence.value
        if (
            persisted.runtime_layout_bootstrap != layout_value
            or layout_value.get("run_id") != invocation.run_id
            or layout_value.get("apply_attempt_id")
            != invocation.apply_attempt_id
            or Path(str(layout_value.get("runtime_root")))
            != invocation.runtime_root
            or tuple(layout_value.get("runtime_root_identity", ()))
            != invocation.runtime_root_identity
        ):
            raise ValueError("prepared_package_install_layout_invalid")
        layout = runtime_layout_evidence
    return PreparedPackageInstall(
        plan=plan,
        runtime_layout_evidence=layout,
        apply_gate=resolved_gate,
    )


def plan_apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    apply_gate: dict[str, Any] | None = None,
    frozen_compiler_inputs: FrozenCompilerInputs | None = None,
) -> dict[str, Any]:
    with lease_package_input(Path(package_root)) as lease:
        package = lease.package_root
        _validate_runtime_apply_package(package)
        resolved_gate = _resolve_allowed_apply_gate(
            package=package,
            apply_gate=apply_gate,
            allow_source_informed=False,
            frozen_compiler_inputs=frozen_compiler_inputs,
        )
        logical_config_dir = _logical_config_dir(package, config_dir)
        return build_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime_root,
            config_dir=logical_config_dir,
            apply_gate=resolved_gate,
        )


def install_runtime_package(
    plan: RuntimeInstallPlan,
    *,
    fault_hook: FaultHook = no_fault,
    transaction_id: str | None = None,
) -> RuntimeInstallResult:
    """Reuse the caller-held output-operation lease when one is bound."""

    context = _ACTIVE_OUTPUT_OPERATION_INSTALL.get()
    if context is None:
        return _install_runtime_package(
            plan,
            fault_hook=fault_hook,
            transaction_id=transaction_id,
        )
    return _install_runtime_package_under_output_operation(
        plan,
        operation_lease=context.operation_lease,
        package_lease=context.package_lease,
        expected_root_identity=context.expected_root_identity,
        fault_hook=fault_hook,
        transaction_id=transaction_id,
    )


@contextmanager
def _bind_output_operation_install(
    *,
    operation_lease: OutputOperationAdmissionLease,
    package_lease: PackageInputLease,
    expected_root_identity: PathIdentity,
) -> Iterator[None]:
    if _ACTIVE_OUTPUT_OPERATION_INSTALL.get() is not None:
        raise RuntimeError("runtime_apply_output_operation_install_reentered")
    context = _OutputOperationInstallContext(
        operation_lease=operation_lease,
        package_lease=package_lease,
        expected_root_identity=tuple(expected_root_identity),
    )
    token = _ACTIVE_OUTPUT_OPERATION_INSTALL.set(context)
    try:
        yield
    finally:
        _ACTIVE_OUTPUT_OPERATION_INSTALL.reset(token)


def apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    replace: bool = True,
    fake_receipt: dict[str, Any] | None = None,
    apply_gate: dict[str, Any] | None = None,
    allow_source_informed: bool = False,
    write_history: bool = True,
) -> dict[str, Any]:
    del replace, write_history
    runtime = Path(runtime_root).absolute()
    _bootstrap_neutral_output_locks()
    with ExitStack() as mutation_stack:
        operation_lease = mutation_stack.enter_context(
            lease_output_operation_admission()
        )
        require_output_operation_allows_runtime_mutation(
            lease=operation_lease
        )
        with _lease_real_apply_input(Path(package_root)) as lease:
            package = lease.package_root
            _validate_runtime_apply_package(package)
            resolved_gate = _resolve_allowed_apply_gate(
                package=package,
                apply_gate=apply_gate,
                allow_source_informed=allow_source_informed,
            )
            logical_config_dir = _logical_config_dir(package, config_dir)
            receipt = fake_receipt
            if receipt is None:
                receipt = build_fake_apply_receipt(
                    package_root=package,
                    runtime_root=runtime,
                    config_dir=logical_config_dir,
                    apply_gate=resolved_gate,
                )
            verify_fake_apply_receipt(
                package_root=package,
                runtime_root=runtime,
                config_dir=logical_config_dir,
                receipt=receipt,
            )
            if lease.publication is None:
                raise TypeError("published_output_required")
            revalidate_package_input_lease(lease)
            published = _published_output(lease)
            if path_lexists(runtime):
                require_plain_directory(runtime)
                require_same_identity_resolution(runtime)
                expected_root_identity = path_identity(runtime)
            else:
                bound_ancestor, bound_ancestor_identity = (
                    _nearest_existing_runtime_ancestor(runtime)
                )
                authorization = (
                    _authorize_legacy_runtime_root_bootstrap_from_context(
                        output_operation_lease=operation_lease,
                        package_lease=lease,
                        runtime_root=runtime,
                        expected_predecessor_identity=None,
                        bound_ancestor_path=bound_ancestor,
                        bound_ancestor_identity=bound_ancestor_identity,
                        config_dir=logical_config_dir,
                        apply_gate=resolved_gate,
                        fake_apply_receipt=receipt,
                    )
                )
                bootstrap_evidence = _bootstrap_legacy_runtime_root_from_context(
                    authorization=authorization,
                )
                expected_root_identity = (
                    bootstrap_evidence.successor_identity
                )
                require_plain_directory(runtime)
                require_same_identity_resolution(runtime)
                if path_identity(runtime) != expected_root_identity:
                    raise ValueError("legacy_runtime_root_successor_changed")
            plan = plan_runtime_install(
                published_output=published,
                runtime_root=runtime,
            )
            if plan.logical_config_dir != logical_config_dir:
                raise ValueError("config_dir_mismatch")
            with _bind_output_operation_install(
                operation_lease=operation_lease,
                package_lease=lease,
                expected_root_identity=expected_root_identity,
            ):
                result = install_runtime_package(plan)
            return _apply_result(plan, result, resolved_gate)


@contextmanager
def _lease_real_apply_input(
    package_input: Path,
) -> Iterator[PackageInputLease]:
    output_root = _direct_published_output_root(package_input)
    lease_target = output_root if output_root is not None else package_input
    with ExitStack() as stack:
        try:
            lease = stack.enter_context(lease_package_input(lease_target))
        except ValueError as error:
            if output_root is not None:
                raise TypeError("published_output_required") from error
            raise
        if output_root is not None:
            if (
                lease.publication is None
                or _resolved(lease.package_root) != _resolved(package_input)
                or package_input.parent.name
                != f"sha256-{lease.content_root_sha256}"
            ):
                raise TypeError("published_output_required")
        yield lease


def _direct_published_output_root(package_input: Path) -> Path | None:
    if (
        package_input.name != "04_package"
        or not _REVISION_NAME.fullmatch(package_input.parent.name)
        or package_input.parent.parent.name != "revisions"
    ):
        return None
    return package_input.parent.parent.parent


def _published_output(lease: PackageInputLease) -> PublishedOutput:
    if (
        lease.publication is None
        or lease.output_root is None
        or lease.content_root_sha256 is None
    ):
        raise TypeError("published_output_required")
    return PublishedOutput(
        output_root=lease.output_root,
        revision_root=lease.package_root.parent,
        package_root=lease.package_root,
        content_root_sha256=lease.content_root_sha256,
        reused_existing_revision=True,
    )


def _apply_result(
    plan: RuntimeInstallPlan,
    result: RuntimeInstallResult,
    apply_gate: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": result.status,
        "runtime_write_performed": result.runtime_write_performed,
        "mapped_deck_name": plan.deck_name,
        "logical_config_dir": plan.logical_config_dir,
        "versioned_config_dir": result.config_dir,
        "package_root_sha256": result.package_root_sha256,
        "previous_config_dir": result.previous_config_dir,
        "receipt_path": (
            str(result.receipt_path)
            if result.receipt_path is not None
            else None
        ),
        "apply_gate": apply_gate,
    }


def _validate_runtime_apply_package(package: Path) -> None:
    try:
        report = validate_complete_package(package)
    except ValueError as exc:
        raise ValueError(
            "Runtime apply requires a valid complete package before fake/apply "
            f"receipt or runtime writes: {exc}"
        ) from exc

    if strict_validation_passed(report):
        return
    errors = report.get("errors") or ["unknown package validation failure"]
    first_error = next(
        (
            code
            for code in (
                LINKED_RUNTIME_OWNER_EVIDENCE_MISSING,
                LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
            )
            if code in errors
        ),
        str(errors[0]),
    )
    extra_count = max(len(errors) - 1, 0)
    suffix = f" (and {extra_count} more)" if extra_count else ""
    raise ValueError(
        "Runtime apply requires a valid complete package before fake/apply "
        f"receipt or runtime writes: {first_error}{suffix}"
    )


def _resolve_allowed_apply_gate(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
    allow_source_informed: bool,
    frozen_compiler_inputs: FrozenCompilerInputs | None = None,
) -> dict[str, Any]:
    del allow_source_informed
    evaluated = evaluate_apply_gate(
        package, **({"frozen_compiler_inputs": frozen_compiler_inputs}
                    if frozen_compiler_inputs is not None else {}),
    )
    if apply_gate is not None and apply_gate != evaluated:
        reason = _first_gate_reason(evaluated)
        raise ValueError(
            "Runtime apply requires an allowed apply gate from "
            f"reports/operator_summary.json; got apply_gate_mismatch:{reason}"
        )
    if not _is_allowed_gate_for_package(
        package=package,
        apply_gate=evaluated,
    ):
        reason = _first_gate_reason(evaluated)
        raise ValueError(
            "Runtime apply requires an allowed apply gate from "
            f"reports/operator_summary.json; got {reason}"
        )
    return evaluated


def _is_allowed_gate_for_package(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
) -> bool:
    if not isinstance(apply_gate, dict):
        return False
    if apply_gate.get("allowed") is not True:
        return False
    if apply_gate.get("mode") != "load_safe_apply":
        return False
    if apply_gate.get("policy") not in {"ALLOWED", "ALLOWED_WITH_WARNINGS"}:
        return False
    operator_summary_path = apply_gate.get("operator_summary_path")
    if not operator_summary_path:
        return False
    expected = package / "reports" / "operator_summary.json"
    try:
        return Path(str(operator_summary_path)).resolve() == expected.resolve()
    except OSError:
        return False


def _first_gate_reason(apply_gate: dict[str, Any] | None) -> str:
    if not isinstance(apply_gate, dict):
        return "missing_apply_gate"
    reasons = apply_gate.get("reasons")
    if isinstance(reasons, list) and reasons:
        first = reasons[0]
        if isinstance(first, dict):
            return str(first.get("reason", "blocked"))
        return str(first)
    status = apply_gate.get("status", "missing_apply_gate")
    mode = apply_gate.get("mode", "")
    return f"{status}:{mode}" if mode else str(status)


def _logical_config_dir(package: Path, requested: str | None) -> str:
    logical = _single_config_dir(package)
    if requested is not None:
        _validate_config_dir(requested)
        if requested != logical:
            raise ValueError("config_dir_mismatch")
    source = package / "CustomConfig" / logical
    _validate_complete_source_dir(source)
    return logical


def _single_config_dir(package_root: Path) -> str:
    custom_config = package_root / "CustomConfig"
    if not custom_config.is_dir():
        raise FileNotFoundError(
            f"Package CustomConfig directory not found: {custom_config}"
        )
    deck_dirs = sorted(
        path.name for path in custom_config.iterdir() if path.is_dir()
    )
    if len(deck_dirs) != 1:
        raise ValueError("Expected exactly one CustomConfig deck directory.")
    return deck_dirs[0]


def _validate_config_dir(config_dir: str) -> None:
    path = Path(config_dir)
    if (
        not config_dir
        or path.name != config_dir
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"Invalid config directory name: {config_dir!r}")


def _validate_complete_source_dir(source_dir: Path) -> None:
    missing = [
        filename
        for filename in ("GlobalValues.json", "Mulligan.json")
        if not (source_dir / filename).is_file()
    ]
    if missing:
        raise ValueError(
            f"Incomplete package deck config {source_dir}: "
            f"missing {', '.join(missing)}"
        )


def _resolved(path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except OSError:
        return path.resolve()
