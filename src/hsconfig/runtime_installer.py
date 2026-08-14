"""Transactional installation of one verified published runtime package."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from hsconfig.atomic_io import (
    ExclusiveFileLock,
    FaultHook,
    atomic_write_bytes,
    no_fault,
)
from hsconfig.current_output import (
    PackageInputLease,
    lease_package_input,
    snapshot_and_verify_revision,
)
from hsconfig.deck_config_ini import (
    DeckConfigSnapshot,
    read_deck_config,
    render_deck_config,
    replace_deck_config_if_unchanged,
)
from hsconfig.output_publisher import PublishedOutput
from hsconfig.package_io import (
    BoundedFilesystemPackageView,
    path_identity,
    path_identity_from_status,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_plain_directory,
    secure_create_directory,
    secure_open_file_descriptor,
    secure_replace,
    secure_rmdir,
    secure_unlink,
    snapshot_bounded_filesystem_package,
    status_is_reparse,
)
from hsconfig.run_manifest import ManifestEntry, TreeManifest, verify_tree_manifest
from hsconfig.runtime_state import (
    RuntimeDeckState,
    RuntimeState,
    read_runtime_state,
    serialize_runtime_state,
)
from hsconfig.runtime_transaction_journal import (
    RuntimeCleanupEntry,
    RuntimeTransactionJournal,
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    read_runtime_transaction_journal,
    runtime_transaction_journal_path,
    runtime_transaction_journal_bytes,
    write_runtime_transaction_journal,
)


_SAFE_COMPONENT_LIMIT = 255
_STATE_SLUG_LIMIT = 48
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSIONED_CONFIG = re.compile(r"^.+--sha256-[0-9a-f]{64}$")
_STATE_IDENTITY_DOMAIN = b"hsconfig-runtime-deck-state-v1\0"
_RECEIPT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class RuntimeInstallPlan:
    deck_name: str
    logical_config_dir: str
    versioned_config_dir: str
    package_root_sha256: str
    source_revision_root: Path
    source_package_root: Path
    runtime_root: Path
    ini_snapshot: DeckConfigSnapshot

    def __post_init__(self) -> None:
        expected = (
            f"{self.logical_config_dir}--sha256-{self.package_root_sha256}"
        )
        if (
            not _valid_deck_name(self.deck_name)
            or not _valid_component(self.logical_config_dir)
            or not _SHA256.fullmatch(self.package_root_sha256)
            or self.versioned_config_dir != expected
            or not _valid_component(self.versioned_config_dir)
            or not isinstance(self.source_revision_root, Path)
            or not isinstance(self.source_package_root, Path)
            or not isinstance(self.runtime_root, Path)
            or not isinstance(self.ini_snapshot, DeckConfigSnapshot)
        ):
            code = (
                "runtime_config_component_too_long"
                if isinstance(self.versioned_config_dir, str)
                and len(self.versioned_config_dir) > _SAFE_COMPONENT_LIMIT
                else "runtime_install_plan_invalid"
            )
            raise ValueError(code)


@dataclass(frozen=True, slots=True)
class RuntimeInstallResult:
    status: Literal[
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ]
    config_dir: str
    package_root_sha256: str
    previous_config_dir: str | None
    receipt_path: Path | None


@dataclass(frozen=True, slots=True)
class _RuntimeFile:
    relative_path: str
    size: int
    sha256: str
    source_path: str


@dataclass(frozen=True, slots=True)
class _RuntimePackageSpec:
    deck_name: str
    logical_config_dir: str
    package_root_sha256: str
    files: tuple[_RuntimeFile, ...]


@dataclass(frozen=True, slots=True)
class _RecoveryOutcome:
    state: RuntimeState | None
    repaired: bool


def plan_runtime_install(
    *,
    published_output: PublishedOutput,
    runtime_root: Path,
) -> RuntimeInstallPlan:
    if not isinstance(published_output, PublishedOutput):
        raise TypeError("published_output_required")
    root = Path(runtime_root)
    require_plain_directory(root)
    if (
        published_output.package_root
        != published_output.revision_root / "04_package"
        or published_output.revision_root.parent.parent
        != published_output.output_root
    ):
        raise ValueError("published_output_invalid")
    verified = snapshot_and_verify_revision(published_output.revision_root)
    if (
        verified.manifest.content_root_sha256
        != published_output.content_root_sha256
    ):
        raise ValueError("published_output_invalid")
    spec = _runtime_package_spec(verified.manifest)
    versioned = (
        f"{spec.logical_config_dir}--sha256-{spec.package_root_sha256}"
    )
    if len(versioned) > _SAFE_COMPONENT_LIMIT:
        raise ValueError("runtime_config_component_too_long")
    ini_path = root / "CustomConfig" / "deck_config.ini"
    if path_lexists(ini_path.parent):
        require_plain_directory(ini_path.parent)
        ini_snapshot = read_deck_config(ini_path, deck_name=spec.deck_name)
    else:
        ini_snapshot = DeckConfigSnapshot(
            path=ini_path,
            existed=False,
            content=None,
            sha256=None,
            selected_config_dir=None,
        )
    return RuntimeInstallPlan(
        deck_name=spec.deck_name,
        logical_config_dir=spec.logical_config_dir,
        versioned_config_dir=versioned,
        package_root_sha256=spec.package_root_sha256,
        source_revision_root=published_output.revision_root,
        source_package_root=published_output.package_root,
        runtime_root=root,
        ini_snapshot=ini_snapshot,
    )


def install_runtime_package(
    plan: RuntimeInstallPlan,
    *,
    fault_hook: FaultHook = no_fault,
) -> RuntimeInstallResult:
    if not isinstance(plan, RuntimeInstallPlan):
        raise TypeError("runtime_install_plan_required")
    output_root = plan.source_revision_root.parent.parent
    with lease_package_input(output_root) as lease:
        spec = _validate_leased_source(plan, lease)
        _ensure_directory(plan.runtime_root / ".hsconfig")
        with ExclusiveFileLock(plan.runtime_root / ".hsconfig" / "apply.lock"):
            try:
                _ensure_runtime_layout(plan.runtime_root)
                fault_hook("after_lock")
                recovery = _recover_locked(plan.runtime_root)
                current_ini = _read_actual_ini(plan)
                if _same_config_dir(
                    current_ini.selected_config_dir,
                    plan.versioned_config_dir,
                ):
                    target = (
                        plan.runtime_root
                        / "CustomConfig"
                        / plan.versioned_config_dir
                    )
                    _verify_runtime_tree_against_spec(target, spec, lease.snapshot)
                    owner = _require_unambiguous_owner(
                        plan.runtime_root,
                        target,
                        plan.package_root_sha256,
                    )
                    del owner
                    state = _repair_selected_state_without_journal(
                        plan,
                        current_ini,
                    )
                    receipt = _receipt_path(
                        plan.runtime_root,
                        _state_key(plan.deck_name),
                    )
                    if not receipt.is_file():
                        _write_receipt(
                            plan.runtime_root,
                            _receipt_payload_for_plan(
                                plan,
                                current_ini.sha256,
                                _state_key(plan.deck_name),
                            ),
                        )
                    del state
                    return RuntimeInstallResult(
                        status=(
                            "recovered" if recovery.repaired else "already_current"
                        ),
                        config_dir=plan.versioned_config_dir,
                        package_root_sha256=plan.package_root_sha256,
                        previous_config_dir=current_ini.selected_config_dir,
                        receipt_path=receipt,
                    )
                return _install_locked(
                    plan,
                    spec,
                    lease.snapshot,
                    current_ini,
                    fault_hook,
                )
            except BaseException as primary:
                try:
                    _recover_locked(plan.runtime_root)
                except BaseException as recovery_error:
                    _add_note(
                        primary,
                        "best-effort runtime recovery failed",
                        recovery_error,
                    )
                raise


def recover_runtime_state(runtime_root: Path) -> RuntimeState | None:
    root = Path(runtime_root)
    require_plain_directory(root)
    _ensure_directory(root / ".hsconfig")
    with ExclusiveFileLock(root / ".hsconfig" / "apply.lock"):
        _ensure_runtime_layout(root)
        return _recover_locked(root).state


def _install_locked(
    plan: RuntimeInstallPlan,
    spec: _RuntimePackageSpec,
    source_snapshot: BoundedFilesystemPackageView | None,
    current_ini: DeckConfigSnapshot,
    fault_hook: FaultHook,
) -> RuntimeInstallResult:
    if source_snapshot is None:
        raise ValueError("runtime_install_source_not_current")
    next_ini = render_deck_config(
        current_ini,
        deck_name=plan.deck_name,
        config_dir=plan.versioned_config_dir,
    )
    next_ini_sha256 = hashlib.sha256(next_ini).hexdigest()
    transaction_id = uuid.uuid4().hex
    state_key = _state_key(plan.deck_name)
    journal = RuntimeTransactionJournal(
        schema_version=1,
        transaction_id=transaction_id,
        deck_name=plan.deck_name,
        source_manifest_sha256=_source_manifest_sha256(plan),
        state_key=state_key,
        logical_config_dir=plan.logical_config_dir,
        package_root_sha256=plan.package_root_sha256,
        candidate_path=f".hsconfig/staging/{transaction_id}",
        target_path=f"CustomConfig/{plan.versioned_config_dir}",
        candidate_identity=None,
        target_identity=None,
        owns_target=False,
        previous_config_dir=current_ini.selected_config_dir,
        next_config_dir=plan.versioned_config_dir,
        previous_ini_sha256=current_ini.sha256,
        next_ini_sha256=next_ini_sha256,
        phase=RuntimeTransactionPhase.PREPARED,
    )
    journal_path = runtime_transaction_journal_path(
        plan.runtime_root,
        transaction_id,
    )
    _write_journal(journal_path, journal)
    candidate = plan.runtime_root / journal.candidate_path
    candidate_identity = secure_create_directory(
        candidate,
        expected_parent_identity=path_identity(candidate.parent),
    )
    journal = replace(journal, candidate_identity=candidate_identity)
    _write_journal(journal_path, journal)

    _copy_runtime_files(candidate, spec, source_snapshot)
    journal = replace(
        journal,
        phase=RuntimeTransactionPhase.RUNTIME_STAGED,
    )
    _write_journal(journal_path, journal)
    fault_hook("after_runtime_staging_copy")

    _verify_runtime_tree_against_spec(candidate, spec, source_snapshot)
    journal = replace(
        journal,
        phase=RuntimeTransactionPhase.RUNTIME_VERIFIED,
    )
    _write_journal(journal_path, journal)
    fault_hook("after_runtime_staging_verify")

    target = plan.runtime_root / journal.target_path
    if path_lexists(target):
        target_identity = _plain_directory_identity(target)
        try:
            _verify_runtime_tree_against_spec(target, spec, source_snapshot)
            _require_unambiguous_owner(
                plan.runtime_root,
                target,
                plan.package_root_sha256,
            )
        except Exception as error:
            raise RuntimeError("runtime_digest_target_conflict") from error
        _remove_owned_tree(candidate, candidate_identity)
        journal = replace(
            journal,
            target_identity=target_identity,
            owns_target=False,
        )
        _write_journal(journal_path, journal)
    else:
        secure_replace(
            candidate,
            target,
            expected_source_identity=candidate_identity,
            expected_source_parent_identity=path_identity(candidate.parent),
            expected_target_parent_identity=path_identity(target.parent),
            expected_target_absent=True,
        )
        fault_hook("after_runtime_revision_rename")
        target_identity = _plain_directory_identity(target)
        if target_identity != candidate_identity:
            raise RuntimeError("runtime_target_identity_changed")
        journal = replace(
            journal,
            target_identity=target_identity,
            owns_target=True,
        )
        _write_journal(journal_path, journal)

    _verify_runtime_tree_against_spec(target, spec, source_snapshot)
    fault_hook("before_ini_compare_and_swap")
    committed_ini_sha256 = replace_deck_config_if_unchanged(
        current_ini,
        next_ini,
    )
    fault_hook("after_ini_compare_and_swap")
    committed_ini = _read_actual_ini(plan)
    if (
        committed_ini.selected_config_dir != plan.versioned_config_dir
        or committed_ini.sha256 != committed_ini_sha256
        or committed_ini_sha256 != next_ini_sha256
    ):
        raise RuntimeError("runtime_ini_commit_verification_failed")
    _verify_runtime_tree_against_spec(target, spec, source_snapshot)
    journal = replace(
        journal,
        target_identity=_plain_directory_identity(target),
        phase=RuntimeTransactionPhase.INI_COMMITTED,
    )
    _write_journal(journal_path, journal)

    fault_hook("before_state_write")
    _write_selected_state(
        plan.runtime_root,
        journal,
        committed_ini_sha256,
    )
    fault_hook("after_state_write")
    journal = replace(
        journal,
        phase=RuntimeTransactionPhase.STATE_COMMITTED,
    )
    _write_journal(journal_path, journal)

    receipt_path = _receipt_path(plan.runtime_root, state_key)
    try:
        fault_hook("before_receipt_write")
        _write_receipt(
            plan.runtime_root,
            _receipt_payload(journal, committed_ini_sha256),
            fault_hook=fault_hook,
        )
    except Exception:
        return RuntimeInstallResult(
            status="committed_receipt_pending",
            config_dir=plan.versioned_config_dir,
            package_root_sha256=plan.package_root_sha256,
            previous_config_dir=current_ini.selected_config_dir,
            receipt_path=None,
        )

    journal = replace(journal, phase=RuntimeTransactionPhase.FINALIZED)
    _write_journal(journal_path, journal)
    fault_hook("before_old_revision_cleanup")
    _cleanup_old_revision(
        plan.runtime_root,
        journal,
        fault_hook=fault_hook,
    )
    if not journal.owns_target:
        _delete_journal(journal_path)
    return RuntimeInstallResult(
        status="applied",
        config_dir=plan.versioned_config_dir,
        package_root_sha256=plan.package_root_sha256,
        previous_config_dir=current_ini.selected_config_dir,
        receipt_path=receipt_path,
    )


def _validate_leased_source(
    plan: RuntimeInstallPlan,
    lease: PackageInputLease,
) -> _RuntimePackageSpec:
    if (
        lease.publication is None
        or lease.snapshot is None
        or lease.content_root_sha256 != _source_manifest_sha256(plan)
        or lease.package_root != plan.source_package_root
        or lease.package_root.parent != plan.source_revision_root
    ):
        raise ValueError("runtime_install_source_not_current")
    manifest = verify_tree_manifest(lease.snapshot)
    spec = _runtime_package_spec(manifest)
    if (
        manifest.content_root_sha256 != _source_manifest_sha256(plan)
        or spec.deck_name != plan.deck_name
        or spec.logical_config_dir != plan.logical_config_dir
        or spec.package_root_sha256 != plan.package_root_sha256
        or plan.versioned_config_dir
        != f"{spec.logical_config_dir}--sha256-{spec.package_root_sha256}"
    ):
        raise ValueError("runtime_install_source_not_current")
    return spec


def _source_manifest_sha256(plan: RuntimeInstallPlan) -> str:
    name = plan.source_revision_root.name
    prefix = "sha256-"
    if not name.startswith(prefix) or not _SHA256.fullmatch(name[len(prefix) :]):
        raise ValueError("runtime_install_plan_invalid")
    return name[len(prefix) :]


def _runtime_package_spec(
    manifest: TreeManifest | None,
) -> _RuntimePackageSpec:
    if manifest is None:
        raise ValueError("runtime_install_source_not_current")
    prefix = "04_package/CustomConfig/"
    selected: list[tuple[ManifestEntry, str, str]] = []
    logical_names: set[str] = set()
    for entry in manifest.entries:
        if not entry.relative_path.startswith(prefix):
            continue
        suffix = entry.relative_path[len(prefix) :]
        if "/" not in suffix:
            raise ValueError("runtime_package_manifest_invalid")
        logical, relative = suffix.split("/", 1)
        if not logical or not relative:
            raise ValueError("runtime_package_manifest_invalid")
        logical_names.add(logical)
        selected.append((entry, logical, relative))
    if len(logical_names) != 1 or not selected:
        raise ValueError("runtime_package_manifest_invalid")
    logical = next(iter(logical_names))
    if not _valid_component(logical):
        raise ValueError("runtime_package_manifest_invalid")
    files = tuple(
        _RuntimeFile(
            relative_path=relative,
            size=entry.size,
            sha256=entry.sha256,
            source_path=entry.relative_path,
        )
        for entry, row_logical, relative in selected
        if row_logical == logical
    )
    paths = tuple(row.relative_path for row in files)
    if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
        raise ValueError("runtime_package_manifest_invalid")
    records = b"".join(
        (
            f"{row.relative_path}\0{row.size}\0{row.sha256}\n"
        ).encode("utf-8")
        for row in files
    )
    return _RuntimePackageSpec(
        deck_name=manifest.deck_name,
        logical_config_dir=logical,
        package_root_sha256=hashlib.sha256(records).hexdigest(),
        files=files,
    )


def _ensure_runtime_layout(runtime_root: Path) -> None:
    require_plain_directory(runtime_root)
    _ensure_directory(runtime_root / "CustomConfig")
    hsconfig = runtime_root / ".hsconfig"
    _ensure_directory(hsconfig)
    _ensure_directory(hsconfig / "transactions")
    _ensure_directory(hsconfig / "staging")
    _ensure_directory(hsconfig / "receipts")


def _ensure_directory(path: Path) -> None:
    target = Path(path)
    if path_lexists(target):
        require_plain_directory(target)
        return
    require_plain_directory(target.parent)
    try:
        secure_create_directory(
            target,
            expected_parent_identity=path_identity(target.parent),
        )
    except FileExistsError:
        require_plain_directory(target)


def _copy_runtime_files(
    candidate: Path,
    spec: _RuntimePackageSpec,
    source_snapshot: BoundedFilesystemPackageView,
) -> None:
    directories = sorted(
        {
            "/".join(row.relative_path.split("/")[:index])
            for row in spec.files
            for index in range(1, len(row.relative_path.split("/")))
        },
        key=lambda value: (value.count("/"), value),
    )
    for relative in directories:
        _ensure_directory(candidate / Path(relative))
    for row in spec.files:
        content = source_snapshot.read_bytes(row.source_path)
        if (
            len(content) != row.size
            or hashlib.sha256(content).hexdigest() != row.sha256
        ):
            raise ValueError("runtime_install_source_not_current")
        target = candidate / Path(row.relative_path)
        descriptor = secure_open_file_descriptor(
            target,
            create=True,
            write=True,
            expected_parent_identity=path_identity(target.parent),
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                status = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(status.st_mode)
                    or status_is_reparse(status)
                    or status.st_nlink != 1
                    or status.st_size != row.size
                ):
                    raise RuntimeError("runtime_staging_write_failed")
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _verify_runtime_tree_against_spec(
    root: Path,
    spec: _RuntimePackageSpec,
    source_snapshot: BoundedFilesystemPackageView | None,
) -> None:
    try:
        snapshot = snapshot_bounded_filesystem_package(root)
        expected_names = tuple(row.relative_path for row in spec.files)
        if snapshot.file_names() != expected_names:
            raise ValueError("membership")
        expected_directories = sorted(
            {
                "/".join(path.split("/")[:index])
                for path in expected_names
                for index in range(1, len(path.split("/")))
            }
        )
        if snapshot.directory_names != tuple(expected_directories):
            raise ValueError("directories")
        for row in spec.files:
            content = snapshot.read_bytes(row.relative_path)
            if (
                len(content) != row.size
                or hashlib.sha256(content).hexdigest() != row.sha256
                or (
                    source_snapshot is not None
                    and content != source_snapshot.read_bytes(row.source_path)
                )
            ):
                raise ValueError("content")
    except Exception as error:
        raise RuntimeError("runtime_package_verification_failed") from error


def _verify_runtime_tree_digest(root: Path, expected_digest: str) -> None:
    try:
        snapshot = snapshot_bounded_filesystem_package(root)
        records = b"".join(
            (
                f"{name}\0{len(content)}\0"
                f"{hashlib.sha256(content).hexdigest()}\n"
            ).encode("utf-8")
            for name in snapshot.file_names()
            for content in (snapshot.read_bytes(name),)
        )
        if hashlib.sha256(records).hexdigest() != expected_digest:
            raise ValueError("digest")
    except Exception as error:
        raise RuntimeError("runtime_package_verification_failed") from error


def _read_actual_ini(plan: RuntimeInstallPlan) -> DeckConfigSnapshot:
    return read_deck_config(
        plan.runtime_root / "CustomConfig" / "deck_config.ini",
        deck_name=plan.deck_name,
    )


def _write_journal(
    path: Path,
    journal: RuntimeTransactionJournal,
) -> None:
    write_runtime_transaction_journal(path, journal)
    if read_runtime_transaction_journal(path) != journal:
        raise RuntimeError("runtime_transaction_journal_commit_failed")


def _recover_locked(runtime_root: Path) -> _RecoveryOutcome:
    repaired = False
    journals = load_runtime_transaction_journals(runtime_root)
    _validate_recovery_ownership(runtime_root, journals)
    for original in journals:
        journal = original
        journal_path = runtime_transaction_journal_path(
            runtime_root,
            journal.transaction_id,
        )
        candidate = runtime_root / journal.candidate_path
        target = runtime_root / journal.target_path
        candidate_identity = _directory_identity_or_none(candidate)
        target_identity = _directory_identity_or_none(target)
        if (
            candidate_identity is not None
            and journal.candidate_identity != candidate_identity
        ):
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
        if journal.cleanup_started:
            if _resume_owned_cleanup(runtime_root, journal):
                repaired = True
            continue
        rename_window = (
            target_identity is not None
            and journal.target_identity is None
            and journal.candidate_identity == target_identity
        )
        if (
            journal.target_identity is not None
            and target_identity != journal.target_identity
        ):
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
        if rename_window:
            journal = replace(
                journal,
                target_identity=target_identity,
                owns_target=True,
            )
            _write_journal(journal_path, journal)
            repaired = True

        ini = read_deck_config(
            runtime_root / "CustomConfig" / "deck_config.ini",
            deck_name=journal.deck_name,
        )
        selected = _same_config_dir(
            ini.selected_config_dir,
            journal.next_config_dir,
        )
        if selected:
            if target_identity is None or ini.sha256 != journal.next_ini_sha256:
                raise RuntimeError("runtime_recovery_committed_target_invalid")
            _verify_runtime_tree_digest(target, journal.package_root_sha256)
            if journal.phase in {
                RuntimeTransactionPhase.PREPARED,
                RuntimeTransactionPhase.RUNTIME_STAGED,
                RuntimeTransactionPhase.RUNTIME_VERIFIED,
            }:
                journal = replace(
                    journal,
                    target_identity=target_identity,
                    owns_target=(
                        journal.owns_target
                        or journal.candidate_identity == target_identity
                    ),
                    phase=RuntimeTransactionPhase.INI_COMMITTED,
                )
                _write_journal(journal_path, journal)
                repaired = True
            if candidate_identity is not None:
                _remove_owned_tree(candidate, candidate_identity)
                repaired = True
            state_before = read_runtime_state(runtime_root)
            expected_state = _write_selected_state(
                runtime_root,
                journal,
                ini.sha256,
            )
            if state_before != expected_state:
                repaired = True
            if journal.phase == RuntimeTransactionPhase.INI_COMMITTED:
                journal = replace(
                    journal,
                    phase=RuntimeTransactionPhase.STATE_COMMITTED,
                )
                _write_journal(journal_path, journal)
                repaired = True
            receipt = _receipt_path(runtime_root, journal.state_key)
            expected_receipt = _receipt_bytes(
                _receipt_payload(journal, ini.sha256)
            )
            if _plain_file_bytes_or_none(receipt) != expected_receipt:
                _write_receipt(
                    runtime_root,
                    _receipt_payload(journal, ini.sha256),
                )
                repaired = True
            if journal.phase == RuntimeTransactionPhase.STATE_COMMITTED:
                journal = replace(
                    journal,
                    phase=RuntimeTransactionPhase.FINALIZED,
                )
                _write_journal(journal_path, journal)
                repaired = True
            _cleanup_old_revision(runtime_root, journal)
            if not journal.owns_target:
                _delete_journal(journal_path)
                repaired = True
            del expected_state
            continue

        if journal.phase in {
            RuntimeTransactionPhase.INI_COMMITTED,
            RuntimeTransactionPhase.STATE_COMMITTED,
        }:
            raise RuntimeError("runtime_recovery_ini_conflict")
        if candidate_identity is not None:
            _remove_owned_tree(candidate, candidate_identity)
            repaired = True
        active = _active_config_dirs(runtime_root)
        if (
            target_identity is not None
            and (journal.owns_target or rename_window)
            and active is not None
            and journal.next_config_dir.casefold() not in active
        ):
            _verify_runtime_tree_digest(target, journal.package_root_sha256)
            _remove_owned_tree(target, target_identity)
            repaired = True
        if journal.phase != RuntimeTransactionPhase.FINALIZED:
            _delete_journal(journal_path)
            repaired = True

    state = read_runtime_state(runtime_root)
    _verify_active_state_targets(runtime_root, state)
    return _RecoveryOutcome(state=state, repaired=repaired)


def _validate_recovery_ownership(
    runtime_root: Path,
    journals: tuple[RuntimeTransactionJournal, ...],
) -> None:
    owned_targets: dict[str, list[RuntimeTransactionJournal]] = {}
    by_transaction_id = {
        journal.transaction_id: journal for journal in journals
    }
    for journal in journals:
        if journal.owns_target:
            owned_targets.setdefault(
                journal.target_path.casefold(),
                [],
            ).append(journal)
    if any(len(owners) != 1 for owners in owned_targets.values()):
        raise RuntimeError("runtime_recovery_ownership_ambiguous")

    staging = runtime_root / ".hsconfig" / "staging"
    count = 0
    with os.scandir(staging) as iterator:
        for entry in iterator:
            count += 1
            if count > 1024:
                raise RuntimeError("runtime_recovery_ownership_ambiguous")
            path = Path(entry.path)
            status = path.lstat()
            journal = by_transaction_id.get(entry.name)
            if (
                journal is None
                or journal.candidate_path
                != f".hsconfig/staging/{entry.name}"
                or journal.candidate_identity is None
                or status_is_reparse(status)
                or not stat.S_ISDIR(status.st_mode)
                or path_identity_from_status(status)
                != journal.candidate_identity
            ):
                raise RuntimeError("runtime_recovery_ownership_ambiguous")


def _write_selected_state(
    runtime_root: Path,
    journal: RuntimeTransactionJournal,
    ini_sha256: str | None,
) -> RuntimeState:
    if ini_sha256 is None:
        raise RuntimeError("runtime_ini_commit_verification_failed")
    current = read_runtime_state(runtime_root)
    decks = [] if current is None else list(current.decks)
    next_deck = RuntimeDeckState(
        state_key=journal.state_key,
        deck_name=journal.deck_name,
        config_dir=journal.next_config_dir,
        package_root_sha256=journal.package_root_sha256,
        ini_sha256=ini_sha256,
    )
    decks = [
        deck
        for deck in decks
        if deck.state_key.casefold() != journal.state_key.casefold()
        and deck.deck_name.casefold() != journal.deck_name.casefold()
    ]
    decks.append(next_deck)
    state = RuntimeState(1, tuple(decks))
    content = serialize_runtime_state(state)
    state_path = runtime_root / ".hsconfig" / "state.json"
    if _plain_file_bytes_or_none(state_path) != content:
        atomic_write_bytes(state_path, content)
    if read_runtime_state(runtime_root) != state:
        raise RuntimeError("runtime_state_commit_verification_failed")
    return state


def _repair_selected_state_without_journal(
    plan: RuntimeInstallPlan,
    ini: DeckConfigSnapshot,
) -> RuntimeState:
    owner = _require_unambiguous_owner(
        plan.runtime_root,
        plan.runtime_root / "CustomConfig" / plan.versioned_config_dir,
        plan.package_root_sha256,
    )
    return _write_selected_state(plan.runtime_root, owner, ini.sha256)


def _receipt_payload(
    journal: RuntimeTransactionJournal,
    ini_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": _RECEIPT_SCHEMA_VERSION,
        "state_key": journal.state_key,
        "deck_name": journal.deck_name,
        "logical_config_dir": journal.logical_config_dir,
        "config_dir": journal.next_config_dir,
        "package_root_sha256": journal.package_root_sha256,
        "source_manifest_sha256": journal.source_manifest_sha256,
        "ini_sha256": ini_sha256,
    }


def _receipt_payload_for_plan(
    plan: RuntimeInstallPlan,
    ini_sha256: str | None,
    state_key: str,
) -> dict[str, object]:
    if ini_sha256 is None:
        raise RuntimeError("runtime_ini_commit_verification_failed")
    return {
        "schema_version": _RECEIPT_SCHEMA_VERSION,
        "state_key": state_key,
        "deck_name": plan.deck_name,
        "logical_config_dir": plan.logical_config_dir,
        "config_dir": plan.versioned_config_dir,
        "package_root_sha256": plan.package_root_sha256,
        "source_manifest_sha256": _source_manifest_sha256(plan),
        "ini_sha256": ini_sha256,
    }


def _receipt_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _write_receipt(
    runtime_root: Path,
    payload: dict[str, object],
    *,
    fault_hook: FaultHook = no_fault,
) -> Path:
    state_key = payload["state_key"]
    if not isinstance(state_key, str) or not _valid_component(state_key):
        raise ValueError("runtime_receipt_invalid")
    directory = runtime_root / ".hsconfig" / "receipts" / state_key
    _ensure_directory(directory)
    path = directory / "last_apply_receipt.json"
    content = _receipt_bytes(payload)

    def receipt_atomic_fault(stage: str) -> None:
        if stage == "after_replace":
            fault_hook("during_receipt_write")

    atomic_write_bytes(path, content, fault_hook=receipt_atomic_fault)
    if _plain_file_bytes_or_none(path) != content:
        raise RuntimeError("runtime_receipt_commit_verification_failed")
    return path


def _receipt_path(runtime_root: Path, state_key: str) -> Path:
    return (
        runtime_root
        / ".hsconfig"
        / "receipts"
        / state_key
        / "last_apply_receipt.json"
    )


def _cleanup_old_revision(
    runtime_root: Path,
    journal: RuntimeTransactionJournal,
    *,
    fault_hook: FaultHook = no_fault,
) -> None:
    hook_called = False

    def cleanup_fault(stage: str) -> None:
        nonlocal hook_called
        hook_called = True
        fault_hook(stage)

    try:
        old_name = journal.previous_config_dir
        if old_name is None or _same_config_dir(
            old_name,
            journal.next_config_dir,
        ):
            return
        active = _active_config_dirs(runtime_root)
        if active is None or old_name.casefold() in active:
            return
        owners = [
            candidate
            for candidate in load_runtime_transaction_journals(runtime_root)
            if candidate.phase == RuntimeTransactionPhase.FINALIZED
            and candidate.owns_target
            and candidate.target_path.casefold()
            == f"CustomConfig/{old_name}".casefold()
        ]
        if len(owners) != 1:
            return
        owner = owners[0]
        old_path = runtime_root / owner.target_path
        if not path_lexists(old_path):
            _delete_journal(
                runtime_transaction_journal_path(
                    runtime_root,
                    owner.transaction_id,
                )
            )
            return
        old_identity = _plain_directory_identity(old_path)
        if owner.target_identity != old_identity:
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
        if owner.cleanup_started:
            _resume_owned_cleanup(
                runtime_root,
                owner,
                fault_hook=cleanup_fault,
            )
            return
        _verify_runtime_tree_digest(old_path, owner.package_root_sha256)
        cleanup = _prepare_cleanup_journal(runtime_root, owner, old_path)
        if cleanup is None:
            return
        _resume_owned_cleanup(
            runtime_root,
            cleanup,
            fault_hook=cleanup_fault,
        )
    finally:
        if not hook_called:
            fault_hook("during_old_revision_cleanup")


def _prepare_cleanup_journal(
    runtime_root: Path,
    owner: RuntimeTransactionJournal,
    target: Path,
) -> RuntimeTransactionJournal | None:
    snapshot = snapshot_bounded_filesystem_package(target)
    file_names = sorted(
        snapshot.file_names(),
        key=lambda value: (value.count("/"), value),
        reverse=True,
    )
    directory_names = sorted(
        snapshot.directory_names,
        key=lambda value: (value.count("/"), value),
        reverse=True,
    )
    entries = tuple(
        RuntimeCleanupEntry(
            kind=kind,
            relative_path=name,
            identity=path_identity(target / Path(name)),
        )
        for kind, names in (
            ("file", file_names),
            ("directory", directory_names),
        )
        for name in names
    )
    cleanup = replace(
        owner,
        cleanup_started=True,
        cleanup_entries=entries,
        cleanup_cursor=0,
    )
    try:
        runtime_transaction_journal_bytes(cleanup)
    except ValueError:
        return None
    _write_journal(
        runtime_transaction_journal_path(
            runtime_root,
            cleanup.transaction_id,
        ),
        cleanup,
    )
    return cleanup


def _resume_owned_cleanup(
    runtime_root: Path,
    journal: RuntimeTransactionJournal,
    *,
    fault_hook: FaultHook = no_fault,
) -> bool:
    if not journal.cleanup_started or journal.target_identity is None:
        raise RuntimeError("runtime_recovery_ownership_ambiguous")
    journal_path = runtime_transaction_journal_path(
        runtime_root,
        journal.transaction_id,
    )
    target = runtime_root / journal.target_path
    active = _active_config_dirs(runtime_root)
    if active is None or journal.next_config_dir.casefold() in active:
        return False
    if not path_lexists(target):
        _delete_journal(journal_path)
        return True
    if _plain_directory_identity(target) != journal.target_identity:
        raise RuntimeError("runtime_recovery_ownership_ambiguous")
    _validate_remaining_cleanup_inventory(target, journal)
    current = journal
    for index in range(journal.cleanup_cursor, len(journal.cleanup_entries)):
        entry = journal.cleanup_entries[index]
        path = target / Path(entry.relative_path)
        if path_lexists(path):
            status = path.lstat()
            if (
                status_is_reparse(status)
                or path_identity_from_status(status) != entry.identity
                or (
                    entry.kind == "file"
                    and (
                        not stat.S_ISREG(status.st_mode)
                        or status.st_nlink != 1
                    )
                )
                or (
                    entry.kind == "directory"
                    and not stat.S_ISDIR(status.st_mode)
                )
            ):
                raise RuntimeError("runtime_recovery_ownership_ambiguous")
            if entry.kind == "file":
                secure_unlink(
                    path,
                    expected_identity=entry.identity,
                    expected_parent_identity=path_identity(path.parent),
                )
            else:
                secure_rmdir(
                    path,
                    expected_identity=entry.identity,
                    expected_parent_identity=path_identity(path.parent),
                )
            fault_hook("during_old_revision_cleanup")
        current = replace(current, cleanup_cursor=index + 1)
        _write_journal(journal_path, current)

    with os.scandir(target) as iterator:
        if any(iterator):
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
    secure_rmdir(
        target,
        expected_identity=journal.target_identity,
        expected_parent_identity=path_identity(target.parent),
    )
    fault_hook("during_old_revision_cleanup")
    _delete_journal(journal_path)
    return True


def _validate_remaining_cleanup_inventory(
    target: Path,
    journal: RuntimeTransactionJournal,
) -> None:
    snapshot = snapshot_bounded_filesystem_package(target)
    expected = {
        (entry.kind, entry.relative_path): (index, entry)
        for index, entry in enumerate(journal.cleanup_entries)
    }
    actual = [
        *(('file', name) for name in snapshot.file_names()),
        *(('directory', name) for name in snapshot.directory_names),
    ]
    for key in actual:
        row = expected.get(key)
        if row is None or row[0] < journal.cleanup_cursor:
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
        path = target / Path(key[1])
        if path_identity(path) != row[1].identity:
            raise RuntimeError("runtime_recovery_ownership_ambiguous")


def _require_unambiguous_owner(
    runtime_root: Path,
    target: Path,
    package_root_sha256: str,
) -> RuntimeTransactionJournal:
    identity = _plain_directory_identity(target)
    relative = target.relative_to(runtime_root).as_posix()
    owners = [
        journal
        for journal in load_runtime_transaction_journals(runtime_root)
        if journal.phase == RuntimeTransactionPhase.FINALIZED
        and journal.owns_target
        and journal.target_path == relative
        and journal.package_root_sha256 == package_root_sha256
        and journal.target_identity == identity
    ]
    if len(owners) != 1:
        raise RuntimeError("runtime_digest_target_conflict")
    return owners[0]


def _active_config_dirs(runtime_root: Path) -> set[str] | None:
    path = runtime_root / "CustomConfig" / "deck_config.ini"
    content = _plain_file_bytes_or_none(path)
    if content is None:
        return set()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    in_configs = False
    seen_decks: set[str] = set()
    configs: set[str] = set()
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_configs = stripped.casefold() == "[configs]"
            continue
        if (
            not in_configs
            or not stripped
            or stripped.startswith(("#", ";"))
            or "=" not in raw
        ):
            continue
        key, value = raw.split("=", 1)
        deck = key.strip().casefold()
        config = value.strip()
        if not deck or deck in seen_decks or not _valid_component(config):
            return None
        seen_decks.add(deck)
        configs.add(config.casefold())
    return configs


def _verify_active_state_targets(
    runtime_root: Path,
    state: RuntimeState | None,
) -> None:
    if state is None:
        return
    active = _active_config_dirs(runtime_root)
    if active is None:
        return
    for deck in state.decks:
        if deck.config_dir.casefold() not in active:
            continue
        target = runtime_root / "CustomConfig" / deck.config_dir
        _verify_runtime_tree_digest(target, deck.package_root_sha256)


def _remove_owned_tree(
    root: Path,
    expected_identity: tuple[int, int, int],
) -> None:
    if _plain_directory_identity(root) != expected_identity:
        raise RuntimeError("runtime_recovery_ownership_ambiguous")
    snapshot = snapshot_bounded_filesystem_package(root)
    for name in sorted(
        snapshot.file_names(),
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        path = root / Path(name)
        status = plain_file_status(path)
        secure_unlink(
            path,
            expected_identity=path_identity_from_status(status),
            expected_parent_identity=path_identity(path.parent),
        )
    for name in sorted(
        snapshot.directory_names,
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        path = root / Path(name)
        secure_rmdir(
            path,
            expected_identity=path_identity(path),
            expected_parent_identity=path_identity(path.parent),
        )
    secure_rmdir(
        root,
        expected_identity=expected_identity,
        expected_parent_identity=path_identity(root.parent),
    )


def _delete_journal(path: Path) -> None:
    if not path_lexists(path):
        return
    status = plain_file_status(path)
    secure_unlink(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=path_identity(path.parent),
    )


def _plain_file_bytes_or_none(path: Path) -> bytes | None:
    if not path_lexists(path):
        return None
    status = plain_file_status(path)
    return read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=1024 * 1024,
    )


def _plain_directory_identity(path: Path) -> tuple[int, int, int]:
    require_plain_directory(path)
    return path_identity(path)


def _directory_identity_or_none(
    path: Path,
) -> tuple[int, int, int] | None:
    if not path_lexists(path):
        return None
    return _plain_directory_identity(path)


def _state_key(deck_name: str) -> str:
    digest = hashlib.sha256(
        _STATE_IDENTITY_DOMAIN + deck_name.casefold().encode("utf-8")
    ).hexdigest()
    normalized = unicodedata.normalize("NFKD", deck_name.casefold())
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-") or "deck"
    slug = slug[:_STATE_SLUG_LIMIT].rstrip("-") or "deck"
    return f"{slug}--sha256-{digest}"


def _same_config_dir(left: str | None, right: str | None) -> bool:
    return (
        left is not None
        and right is not None
        and left.casefold() == right.casefold()
    )


def _valid_deck_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= _SAFE_COMPONENT_LIMIT
        and not value.startswith((";", "#"))
        and not any(character in value for character in "\r\n=\0")
        and not any(ord(character) < 32 for character in value)
    )


def _valid_component(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= _SAFE_COMPONENT_LIMIT
        and value not in {".", ".."}
        and Path(value).name == value
        and not any(character in value for character in '<>:"/\\|?*\0')
        and not any(ord(character) < 32 for character in value)
        and not value.endswith((".", " "))
    )


def _add_note(
    primary: BaseException,
    operation: str,
    error: BaseException,
) -> None:
    try:
        primary.add_note(f"{operation}: {type(error).__name__}: {error}")
    except BaseException:
        pass


__all__ = (
    "RuntimeInstallPlan",
    "RuntimeInstallResult",
    "install_runtime_package",
    "plan_runtime_install",
    "recover_runtime_state",
)
