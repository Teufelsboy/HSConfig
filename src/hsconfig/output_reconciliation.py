"""Conservatively reconcile the twelve canonical HSConfig outputs."""

from __future__ import annotations

import json
import os
import re
import stat
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, NamedTuple


from hsconfig.audited_build_request import render_all_audited_configure_runs
from hsconfig.atomic_io import (
    ExclusiveFileLock,
    LockTimeoutError,
    no_fault,
)
from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    render_configure_run_model,
)
from hsconfig.current_output import (
    lease_package_input,
    snapshot_and_verify_revision,
)
from hsconfig.output_inventory import (
    CANONICAL_DECK_LAYOUT,
    CatalogAuthority as _CatalogAuthority,
    OutputInventory,
    REVISION_NAME_RE,
    ScanContext,
    inventory_is_current as _inventory_is_current,
    load_catalog_authority as _load_catalog_authority,
    scan_inventory as _scan_inventory_with_context,
)
from hsconfig.output_publisher import (
    publish_configure_run,
    validate_finalized_publication_authority,
)
from hsconfig.package_io import (
    FilesystemPathGuard,
    capture_plain_ancestor_guard,
    path_identity,
    path_identity_from_status,
    plain_file_status,
    read_file_no_follow,
    require_plain_directory,
    secure_create_directory,
    secure_replace,
    secure_rmdir,
    secure_unlink,
)


_LEGACY_CONFIGURE_LAYOUT = frozenset(
    {
        "01_manifest",
        "02_source_acquisition",
        "02_source_documents",
        "03_research",
        "03_source_autopilot",
        "04_package",
        "configure_summary.json",
    }
)
_LEGACY_PACKAGE_LAYOUT = frozenset({"CustomConfig", "reports"})
_ROOT_TRANSACTION_NAME = ".hsconfig-output-reconcile-transaction"
_ROOT_ELECTION_NAME = ".hsconfig-output-reconcile.lock"
_ROOT_PREPARE_PREFIX = ".hsconfig-output-reconcile-prepare-"
_ROOT_CLEANUP_PREFIX = ".hsconfig-output-reconcile-cleanup-"
_ROOT_JOURNAL_NAME = "journal.ndjson"
_ROOT_TRANSACTION_SCHEMA = 2
_ROOT_TRANSACTION_PHASES = frozenset(
    {
        "building",
        "staged_ready",
        "previous_moved",
        "live_committed",
        "terminal",
        "aborting",
        "aborted",
    }
)
_ROOT_TRANSITIONS = frozenset(
    {
        ("building", "staged_ready"),
        ("building", "aborting"),
        ("aborting", "aborted"),
        ("staged_ready", "previous_moved"),
        ("previous_moved", "live_committed"),
        ("live_committed", "terminal"),
    }
)
_ROOT_JOURNAL_RECORD_LIMIT = 2_000_000
_ROOT_JOURNAL_GENERATION_LIMIT = 8
_ZERO_RECORD_HASH = "sha256:" + "0" * 64
_APPROVAL_SCHEMA = 1
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


FaultHook = Callable[[str], None]


class _TreeNode(NamedTuple):
    relative_path: str
    identity: tuple[int, int, int]
    node_type: str
    size: int
    content_sha256: str | None


@dataclass(frozen=True, slots=True)
class _DeletionEntry:
    path: Path
    relative_root: str
    identity: tuple[int, int, int]
    deck_name: str
    nodes: tuple[_TreeNode, ...]
    tree_sha256: str


@dataclass(frozen=True, slots=True)
class LegacyDeletionProposal:
    manifest_bytes: bytes
    approval_digest: str

    @property
    def manifest(self) -> Mapping[str, Any]:
        value = json.loads(self.manifest_bytes.decode("utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("reconcile_legacy_manifest_invalid")
        return value


@dataclass(frozen=True, slots=True)
class _RootTransaction:
    transaction_id: str
    outputs_name: str
    parent_identity: tuple[int, int, int]
    transaction_identity: tuple[int, int, int]
    journal_identity: tuple[int, int, int]
    live_identity: tuple[int, int, int] | None
    staged_identity: tuple[int, int, int]
    previous_identity: tuple[int, int, int] | None
    approval_digest: str | None
    legacy_manifest: Mapping[str, Any]
    phase: str


@dataclass(frozen=True, slots=True)
class _JournalState:
    transaction: _RootTransaction
    generation: int
    record_hash: str
    valid_length: int
    has_partial_tail: bool


def propose_legacy_deletion(
    *,
    outputs_root: Path,
    catalog_path: Path,
) -> LegacyDeletionProposal:
    """Return the exact read-only legacy deletion proposal for review."""

    root = Path(os.path.abspath(outputs_root))
    authority = _load_catalog_authority(catalog_path)
    manifest = _deletion_manifest_document(
        root,
        _capture_deletion_manifest(root, authority),
    )
    manifest_bytes = _canonical_json_bytes(manifest)
    return LegacyDeletionProposal(
        manifest_bytes=manifest_bytes,
        approval_digest=f"sha256:{sha256(manifest_bytes).hexdigest()}",
    )


def apply_audited_outputs(
    *,
    outputs_root: Path,
    catalog_path: Path,
    legacy_approval_digest: str | None = None,
    fault_hook: FaultHook = no_fault,
) -> OutputInventory:
    """Recover or rebuild all audited outputs through one durable root swap."""

    root = Path(os.path.abspath(outputs_root))
    authority = _load_catalog_authority(catalog_path)
    election_guard = capture_plain_ancestor_guard(root.parent)
    if (
        not election_guard.rows
        or election_guard.rows[-1][0] != root.parent
    ):
        raise ValueError("filesystem_path_identity_changed")
    election_parent_identity = election_guard.rows[-1][1]
    try:
        with ExclusiveFileLock(
            root.parent / _ROOT_ELECTION_NAME,
            timeout_seconds=0,
            expected_parent_identity=election_parent_identity,
            path_guard=election_guard,
        ):
            election_guard.validate()
            fault_hook("after_election_acquired")
            _apply_audited_outputs_under_election(
                root,
                authority,
                catalog_path=catalog_path,
                legacy_approval_digest=legacy_approval_digest,
                fault_hook=fault_hook,
            )
            result = _scan_public_inventory(root, authority)
            election_guard.validate()
            return result
    except LockTimeoutError as error:
        raise ValueError("reconcile_election_active") from error


def _apply_audited_outputs_under_election(
    root: Path,
    authority: _CatalogAuthority,
    *,
    catalog_path: Path,
    legacy_approval_digest: str | None,
    fault_hook: FaultHook,
) -> None:
    recovered = _recover_root_transaction(
        root,
        authority,
        legacy_approval_digest=legacy_approval_digest,
        fault_hook=fault_hook,
    )
    if recovered is not None:
        return
    current = _scan_inventory(root, authority)
    if _inventory_is_current(current):
        return

    proposal = propose_legacy_deletion(
        outputs_root=root,
        catalog_path=catalog_path,
    )
    manifest = proposal.manifest
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ValueError("reconcile_legacy_manifest_invalid")
    if entries:
        if legacy_approval_digest is None:
            raise ValueError("reconcile_legacy_approval_required")
        if legacy_approval_digest != proposal.approval_digest:
            raise ValueError("reconcile_legacy_approval_mismatch")
    elif legacy_approval_digest is not None and (
        legacy_approval_digest != proposal.approval_digest
    ):
        raise ValueError("reconcile_legacy_approval_mismatch")

    _start_root_transaction(
        root,
        authority,
        proposal=proposal,
        fault_hook=fault_hook,
    )


def _start_root_transaction(
    root: Path,
    authority: _CatalogAuthority,
    *,
    proposal: LegacyDeletionProposal,
    fault_hook: FaultHook,
) -> OutputInventory:
    parent_guard = capture_plain_ancestor_guard(root.parent)
    parent_identity = path_identity(root.parent)
    if _locate_root_coordinator(root.parent) is not None:
        raise ValueError("reconcile_transaction_preexisting")
    fault_hook("before_prepare_directory_create")
    transaction_id = uuid.uuid4().hex
    prepare_root = root.parent / f"{_ROOT_PREPARE_PREFIX}{transaction_id}"
    transaction_identity = secure_create_directory(
        prepare_root,
        expected_parent_identity=parent_identity,
    )
    fault_hook("after_prepare_directory_create")
    fault_hook("after_transaction_directory_create")
    staged_root = prepare_root / "staged"
    staged_identity = secure_create_directory(
        staged_root,
        expected_parent_identity=transaction_identity,
    )
    lease_path = prepare_root / "lease.lock"
    prepare_guard = _capture_expected_directory_guard(
        prepare_root,
        transaction_identity,
    )
    with ExclusiveFileLock(
        lease_path,
        timeout_seconds=0,
        expected_parent_identity=transaction_identity,
        path_guard=prepare_guard,
    ):
        pass
    journal_path = prepare_root / _ROOT_JOURNAL_NAME
    journal_identity = _create_empty_journal(
        journal_path,
        expected_parent_identity=transaction_identity,
    )
    manifest = proposal.manifest
    transaction = _RootTransaction(
        transaction_id=transaction_id,
        outputs_name=root.name,
        parent_identity=parent_identity,
        transaction_identity=transaction_identity,
        journal_identity=journal_identity,
        live_identity=_parse_identity_or_none(manifest.get("outputs_identity")),
        staged_identity=staged_identity,
        previous_identity=None,
        approval_digest=(
            proposal.approval_digest if manifest.get("entries") else None
        ),
        legacy_manifest=manifest,
        phase="building",
    )
    state = _append_root_transition(
        journal_path,
        None,
        transaction,
        fault_hook=fault_hook,
    )
    fault_hook("after_building_journal")
    transaction_root = root.parent / _ROOT_TRANSACTION_NAME
    fault_hook("before_active_rename")
    secure_replace(
        prepare_root,
        transaction_root,
        expected_source_identity=transaction_identity,
        expected_source_parent_identity=parent_identity,
        expected_target_parent_identity=parent_identity,
        expected_target_absent=True,
    )
    fault_hook("after_prepare_published")
    staged_root = transaction_root / "staged"
    journal_path = transaction_root / _ROOT_JOURNAL_NAME
    lease_path = transaction_root / "lease.lock"
    tombstone: Path | None = None
    pending_error: Exception | None = None
    active_guard = _capture_expected_directory_guard(
        transaction_root,
        transaction_identity,
    )
    try:
        with ExclusiveFileLock(
            lease_path,
            timeout_seconds=0,
            expected_parent_identity=transaction_identity,
            path_guard=active_guard,
            create_if_missing=False,
        ):
            fault_hook("after_active_lease_acquired")
            state, current_path = _load_root_transaction(
                transaction_root,
                expected_outputs_name=root.name,
            )
            if current_path != journal_path or state.transaction != transaction:
                raise ValueError("reconcile_transaction_changed")
            try:
                rendered = _build_rendered_audited_runs(authority)
                _require_complete_rendered_set(rendered, authority)
                for deck_name in authority.names:
                    publish_configure_run(
                        rendered[deck_name],
                        staged_root / deck_name,
                    )
                fault_hook("before_staged_verification")
                staged_inventory = _scan_inventory(
                    staged_root,
                    authority,
                    expected_root_identity=staged_identity,
                )
                if not _inventory_is_current(staged_inventory):
                    raise ValueError("reconcile_staged_inventory_invalid")
            except Exception as error:
                state = _append_root_transition(
                    journal_path,
                    state,
                    replace(state.transaction, phase="aborting"),
                    fault_hook=fault_hook,
                )
                _remove_process_owned_tree(
                    staged_root,
                    expected_identity=staged_identity,
                    expected_parent_identity=transaction_identity,
                    fault_hook=fault_hook,
                )
                fault_hook("after_abort_staging_rmdir")
                state = _append_root_transition(
                    journal_path,
                    state,
                    replace(state.transaction, phase="aborted"),
                    fault_hook=fault_hook,
                )
                pending_error = error
            else:
                state = _append_root_transition(
                    journal_path,
                    state,
                    replace(state.transaction, phase="staged_ready"),
                    fault_hook=fault_hook,
                )
                fault_hook("after_staged_ready")
                result, state = _continue_root_transaction(
                    root,
                    authority,
                    state,
                    journal_path=journal_path,
                    parent_guard=parent_guard,
                    fault_hook=fault_hook,
                )
        tombstone = _publish_cleanup_tombstone(
            transaction_root,
            state.transaction,
            fault_hook=fault_hook,
        )
    finally:
        if tombstone is not None:
            _cleanup_tombstone(tombstone, state, fault_hook=fault_hook)
    if pending_error is not None:
        raise pending_error.with_traceback(pending_error.__traceback__)
    return result


def _recover_root_transaction(
    root: Path,
    authority: _CatalogAuthority,
    *,
    legacy_approval_digest: str | None,
    fault_hook: FaultHook,
) -> OutputInventory | None:
    transaction_root = _locate_root_coordinator(root.parent)
    if transaction_root is None:
        return None
    state, journal_path = _load_root_transaction(
        transaction_root,
        expected_outputs_name=root.name,
    )
    _require_recovery_approval(state.transaction, legacy_approval_digest)
    if transaction_root.name.startswith(_ROOT_PREPARE_PREFIX):
        transaction_root, state, journal_path = _adopt_prepared_transaction(
            root,
            authority,
            transaction_root,
            state,
            journal_path,
            fault_hook=fault_hook,
        )
    tombstone: Path | None = None
    result: OutputInventory | None = None
    transaction_guard = _capture_expected_directory_guard(
        transaction_root,
        state.transaction.transaction_identity,
    )
    allow_recovery_lease_create = _journal_only_cleanup_lock_may_create(
        transaction_root,
        state,
        journal_path,
    )
    try:
        with ExclusiveFileLock(
            transaction_root / "lease.lock",
            timeout_seconds=0,
            expected_parent_identity=state.transaction.transaction_identity,
            path_guard=transaction_guard,
            create_if_missing=allow_recovery_lease_create,
        ):
            current, current_path = _load_root_transaction(
                transaction_root,
                expected_outputs_name=root.name,
            )
            if current != state or current_path != journal_path:
                raise ValueError("reconcile_transaction_changed")
            state = current
            transaction = state.transaction
            _validate_root_transaction_authority(transaction, authority)
            parent_guard = capture_plain_ancestor_guard(root.parent)
            if path_identity(root.parent) != transaction.parent_identity:
                raise ValueError("filesystem_path_identity_changed")
            inferred_phase = _reconstruct_root_phase(
                root,
                transaction_root,
                transaction,
                authority,
            )
            state = _append_inferred_transitions(
                journal_path,
                state,
                inferred_phase,
                fault_hook=fault_hook,
            )
            transaction = state.transaction
            if transaction.phase == "building":
                state = _append_root_transition(
                    journal_path,
                    state,
                    replace(transaction, phase="aborting"),
                    fault_hook=fault_hook,
                )
                transaction = state.transaction
            if transaction.phase == "aborting":
                _remove_process_owned_tree(
                    transaction_root / "staged",
                    expected_identity=transaction.staged_identity,
                    expected_parent_identity=(
                        transaction.transaction_identity
                    ),
                    fault_hook=fault_hook,
                )
                fault_hook("after_abort_staging_rmdir")
                state = _append_root_transition(
                    journal_path,
                    state,
                    replace(transaction, phase="aborted"),
                    fault_hook=fault_hook,
                )
            elif transaction.phase in {"aborted", "terminal"}:
                pass
            else:
                result, state = _continue_root_transaction(
                    root,
                    authority,
                    state,
                    journal_path=journal_path,
                    parent_guard=parent_guard,
                    fault_hook=fault_hook,
                )
        tombstone = _publish_cleanup_tombstone(
            transaction_root,
            state.transaction,
            fault_hook=fault_hook,
        )
    except LockTimeoutError as error:
        raise ValueError("reconcile_transaction_active") from error
    finally:
        if tombstone is not None:
            _cleanup_tombstone(tombstone, state, fault_hook=fault_hook)
    return result


def _adopt_prepared_transaction(
    root: Path,
    authority: _CatalogAuthority,
    prepare_root: Path,
    state: _JournalState,
    journal_path: Path,
    *,
    fault_hook: FaultHook,
) -> tuple[Path, _JournalState, Path]:
    """Promote one fully journaled prepare directory under parent election."""

    transaction = state.transaction
    _validate_prepared_transaction(
        root,
        authority,
        prepare_root,
        state,
        journal_path,
    )
    prepare_guard = _capture_expected_directory_guard(
        prepare_root,
        transaction.transaction_identity,
    )
    try:
        with ExclusiveFileLock(
            prepare_root / "lease.lock",
            timeout_seconds=0,
            expected_parent_identity=transaction.transaction_identity,
            path_guard=prepare_guard,
            create_if_missing=False,
        ):
            current, current_path = _load_root_transaction(
                prepare_root,
                expected_outputs_name=root.name,
            )
            if current != state or current_path != journal_path:
                raise ValueError("reconcile_transaction_changed")
            _validate_prepared_transaction(
                root,
                authority,
                prepare_root,
                current,
                current_path,
            )
    except LockTimeoutError as error:
        raise ValueError("reconcile_transaction_active") from error

    active_root = root.parent / _ROOT_TRANSACTION_NAME
    secure_replace(
        prepare_root,
        active_root,
        expected_source_identity=transaction.transaction_identity,
        expected_source_parent_identity=transaction.parent_identity,
        expected_target_parent_identity=transaction.parent_identity,
        expected_target_absent=True,
    )
    fault_hook("after_prepare_adopted")
    return active_root, state, active_root / _ROOT_JOURNAL_NAME


def _validate_prepared_transaction(
    root: Path,
    authority: _CatalogAuthority,
    prepare_root: Path,
    state: _JournalState,
    journal_path: Path,
) -> None:
    transaction = state.transaction
    expected_names = {_ROOT_JOURNAL_NAME, "lease.lock", "staged"}
    if (
        transaction.phase != "building"
        or transaction.previous_identity is not None
        or {entry.name for entry in _plain_scandir(prepare_root)}
        != expected_names
        or path_identity(root.parent) != transaction.parent_identity
        or path_identity(prepare_root) != transaction.transaction_identity
        or journal_path != prepare_root / _ROOT_JOURNAL_NAME
        or path_identity(journal_path) != transaction.journal_identity
    ):
        raise ValueError("reconcile_prepare_invalid")
    try:
        plain_file_status(prepare_root / "lease.lock")
        require_plain_directory(prepare_root / "staged")
        if (
            path_identity(prepare_root / "staged")
            != transaction.staged_identity
        ):
            raise ValueError("reconcile_prepare_invalid")
    except (FileNotFoundError, ValueError) as error:
        raise ValueError("reconcile_prepare_invalid") from error
    _validate_root_transaction_authority(transaction, authority)
    _require_approval_manifest_current(root, transaction)


def _continue_root_transaction(
    root: Path,
    authority: _CatalogAuthority,
    state: _JournalState,
    *,
    journal_path: Path,
    parent_guard: FilesystemPathGuard,
    fault_hook: FaultHook,
) -> tuple[OutputInventory, _JournalState]:
    transaction_root = journal_path.parent
    staged_root = transaction_root / "staged"
    previous_root = transaction_root / "previous"
    transaction = state.transaction
    parent_guard.validate()
    if transaction.phase == "staged_ready":
        _require_staged_authority(staged_root, transaction, authority)
        _require_approval_manifest_current(root, transaction)
        fault_hook("before_live_to_previous")
        parent_guard.validate()
        if transaction.live_identity is not None:
            live_identity = _path_identity_or_none(root)
            previous_identity = _path_identity_or_none(previous_root)
            if (
                live_identity == transaction.live_identity
                and previous_identity is None
            ):
                secure_replace(
                    root,
                    previous_root,
                    expected_source_identity=transaction.live_identity,
                    expected_source_parent_identity=transaction.parent_identity,
                    expected_target_parent_identity=(
                        transaction.transaction_identity
                    ),
                    expected_target_absent=True,
                )
                fault_hook("after_live_to_previous")
            elif not (
                live_identity is None
                and previous_identity == transaction.live_identity
            ):
                raise ValueError("reconcile_transaction_live_move_invalid")
            previous_identity = transaction.live_identity
        else:
            if _path_identity_or_none(root) is not None:
                raise ValueError("reconcile_transaction_live_move_invalid")
            previous_identity = None
        transaction = replace(
            transaction,
            previous_identity=previous_identity,
            phase="previous_moved",
        )
        state = _append_root_transition(
            journal_path,
            state,
            transaction,
            fault_hook=fault_hook,
        )
        fault_hook("after_previous_moved_journal")

    if transaction.phase == "previous_moved":
        fault_hook("before_staged_to_live")
        parent_guard.validate()
        staged_identity = _path_identity_or_none(staged_root)
        live_identity = _path_identity_or_none(root)
        if (
            staged_identity == transaction.staged_identity
            and live_identity is None
        ):
            secure_replace(
                staged_root,
                root,
                expected_source_identity=transaction.staged_identity,
                expected_source_parent_identity=(
                    transaction.transaction_identity
                ),
                expected_target_parent_identity=transaction.parent_identity,
                expected_target_absent=True,
            )
            fault_hook("after_staged_to_live")
        elif not (
            staged_identity is None
            and live_identity == transaction.staged_identity
        ):
            raise ValueError("reconcile_transaction_staged_move_invalid")
        result = _scan_inventory(
            root,
            authority,
            expected_root_identity=transaction.staged_identity,
        )
        if not _inventory_is_current(result):
            raise ValueError("reconcile_final_inventory_invalid")
        transaction = replace(
            transaction,
            phase="live_committed",
        )
        state = _append_root_transition(
            journal_path,
            state,
            transaction,
            fault_hook=fault_hook,
        )
        fault_hook("after_live_committed")

    if transaction.phase != "live_committed":
        raise ValueError("reconcile_transaction_phase_invalid")
    if _path_identity_or_none(root) != transaction.staged_identity:
        raise ValueError("reconcile_transaction_live_identity_invalid")
    result = _scan_inventory(
        root,
        authority,
        expected_root_identity=transaction.staged_identity,
    )
    if not _inventory_is_current(result):
        raise ValueError("reconcile_final_inventory_invalid")
    fault_hook("before_previous_cleanup")
    _remove_approved_previous(
        previous_root,
        transaction,
        fault_hook=fault_hook,
    )
    fault_hook("after_previous_cleanup")
    transaction = replace(transaction, phase="terminal")
    state = _append_root_transition(
        journal_path,
        state,
        transaction,
        fault_hook=fault_hook,
    )
    fault_hook("before_transaction_cleanup")
    return result, state


def _root_transaction_document(
    transaction: _RootTransaction,
) -> dict[str, Any]:
    return {
        "schema_version": _ROOT_TRANSACTION_SCHEMA,
        "transaction_id": transaction.transaction_id,
        "outputs_name": transaction.outputs_name,
        "parent_identity": list(transaction.parent_identity),
        "transaction_identity": list(transaction.transaction_identity),
        "journal_identity": list(transaction.journal_identity),
        "live_identity": _identity_json(transaction.live_identity),
        "staged_identity": list(transaction.staged_identity),
        "previous_identity": _identity_json(transaction.previous_identity),
        "approval_digest": transaction.approval_digest,
        "legacy_manifest": transaction.legacy_manifest,
        "phase": transaction.phase,
    }


def _create_empty_journal(
    path: Path,
    *,
    expected_parent_identity: tuple[int, int, int],
) -> tuple[int, int, int]:
    if path_identity(path.parent) != expected_parent_identity:
        raise ValueError("filesystem_path_identity_changed")
    flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags, 0o600)
    try:
        node_stat = os.fstat(descriptor)
        if not stat.S_ISREG(node_stat.st_mode) or node_stat.st_nlink != 1:
            raise ValueError("reconcile_transaction_journal_invalid")
        os.fsync(descriptor)
        identity = path_identity_from_status(node_stat)
    finally:
        os.close(descriptor)
    if path_identity(path) != identity:
        raise ValueError("reconcile_transaction_journal_identity_changed")
    return identity


def _append_root_transition(
    journal_path: Path,
    state: _JournalState | None,
    transaction: _RootTransaction,
    *,
    fault_hook: FaultHook,
) -> _JournalState:
    flags = (
        os.O_RDWR
        | os.O_APPEND
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(journal_path, flags)
    try:
        node_stat = os.fstat(descriptor)
        if (
            not stat.S_ISREG(node_stat.st_mode)
            or node_stat.st_nlink != 1
            or path_identity_from_status(node_stat) != transaction.journal_identity
        ):
            raise ValueError("reconcile_transaction_journal_identity_changed")
        raw = _read_journal_descriptor(descriptor)
        if state is None:
            if raw:
                raise ValueError("reconcile_transaction_changed")
            generation = 0
            previous_hash = _ZERO_RECORD_HASH
            if transaction.phase != "building":
                raise ValueError("reconcile_transaction_phase_invalid")
            valid_length = 0
        else:
            current = _parse_root_journal(raw)
            if replace(current, has_partial_tail=False) != replace(
                state,
                has_partial_tail=False,
            ):
                raise ValueError("reconcile_transaction_changed")
            if current.has_partial_tail:
                os.ftruncate(descriptor, current.valid_length)
                os.fsync(descriptor)
            generation = current.generation + 1
            previous_hash = current.record_hash
            valid_length = current.valid_length
            _validate_transition(current.transaction, transaction)
        if generation > _ROOT_JOURNAL_GENERATION_LIMIT:
            raise ValueError("reconcile_transaction_generation_overflow")
        body = {
            "generation": generation,
            "previous_record_sha256": previous_hash,
            "schema_version": _ROOT_TRANSACTION_SCHEMA,
            "transaction": _root_transaction_document(transaction),
        }
        record_hash = f"sha256:{sha256(_canonical_json_bytes(body)).hexdigest()}"
        record = {**body, "record_sha256": record_hash}
        line = _canonical_json_bytes(record) + b"\n"
        if len(line) > _ROOT_JOURNAL_RECORD_LIMIT:
            raise ValueError("reconcile_transaction_record_overflow")
        stage = transaction.phase
        fault_hook(f"before_journal_{stage}_append")
        split_at = max(1, len(line) // 2)
        _write_descriptor_all(descriptor, line[:split_at])
        fault_hook(f"during_journal_{stage}_append")
        _write_descriptor_all(descriptor, line[split_at:])
        os.fsync(descriptor)
        fault_hook(f"after_journal_{stage}_append")
        return _JournalState(
            transaction=transaction,
            generation=generation,
            record_hash=record_hash,
            valid_length=valid_length + len(line),
            has_partial_tail=False,
        )
    finally:
        os.close(descriptor)


def _read_journal_descriptor(descriptor: int) -> bytes:
    maximum = _ROOT_JOURNAL_RECORD_LIMIT * (_ROOT_JOURNAL_GENERATION_LIMIT + 1)
    size = os.fstat(descriptor).st_size
    if size > maximum:
        raise ValueError("reconcile_transaction_journal_overflow")
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1 << 20))
        if not chunk:
            raise ValueError("reconcile_transaction_journal_short_read")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _write_descriptor_all(descriptor: int, content: bytes) -> None:
    view = memoryview(content)
    written = 0
    while written < len(view):
        count = os.write(descriptor, view[written:])
        if count <= 0:
            raise OSError("reconcile_transaction_journal_short_write")
        written += count


def _parse_root_journal(raw: bytes) -> _JournalState:
    if not raw:
        raise ValueError("reconcile_transaction_invalid")
    last_newline = raw.rfind(b"\n")
    if last_newline < 0:
        raise ValueError("reconcile_transaction_invalid")
    complete = raw[: last_newline + 1]
    tail = raw[last_newline + 1 :]
    if len(tail) > _ROOT_JOURNAL_RECORD_LIMIT:
        raise ValueError("reconcile_transaction_journal_overflow")
    lines = complete[:-1].split(b"\n")
    if (
        not lines
        or len(lines) > _ROOT_JOURNAL_GENERATION_LIMIT + 1
        or any(not line or len(line) + 1 > _ROOT_JOURNAL_RECORD_LIMIT for line in lines)
    ):
        raise ValueError("reconcile_transaction_invalid")
    previous: _RootTransaction | None = None
    previous_hash = _ZERO_RECORD_HASH
    transaction: _RootTransaction | None = None
    record_hash = ""
    valid_length = 0
    for generation, line in enumerate(lines):
        try:
            record = json.loads(line.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("reconcile_transaction_invalid") from error
        if not isinstance(record, Mapping) or set(record) != {
            "generation",
            "previous_record_sha256",
            "record_sha256",
            "schema_version",
            "transaction",
        }:
            raise ValueError("reconcile_transaction_invalid")
        if line != _canonical_json_bytes(record):
            raise ValueError("reconcile_transaction_noncanonical")
        body = dict(record)
        claimed_hash = body.pop("record_sha256")
        expected_hash = f"sha256:{sha256(_canonical_json_bytes(body)).hexdigest()}"
        if (
            record["schema_version"] != _ROOT_TRANSACTION_SCHEMA
            or record["generation"] != generation
            or record["previous_record_sha256"] != previous_hash
            or claimed_hash != expected_hash
        ):
            raise ValueError("reconcile_transaction_hash_chain_invalid")
        transaction = _parse_root_transaction_document(record["transaction"])
        if generation == 0:
            if transaction.phase != "building":
                raise ValueError("reconcile_transaction_phase_invalid")
        else:
            if previous is None:
                raise ValueError("reconcile_transaction_invalid")
            _validate_transition(previous, transaction)
        previous = transaction
        previous_hash = expected_hash
        record_hash = expected_hash
        valid_length += len(line) + 1
    if transaction is None:
        raise ValueError("reconcile_transaction_invalid")
    return _JournalState(
        transaction=transaction,
        generation=len(lines) - 1,
        record_hash=record_hash,
        valid_length=valid_length,
        has_partial_tail=bool(tail),
    )


def _parse_root_transaction_document(value: Any) -> _RootTransaction:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "transaction_id",
        "outputs_name",
        "parent_identity",
        "transaction_identity",
        "journal_identity",
        "live_identity",
        "staged_identity",
        "previous_identity",
        "approval_digest",
        "legacy_manifest",
        "phase",
    }:
        raise ValueError("reconcile_transaction_invalid")
    if value["schema_version"] != _ROOT_TRANSACTION_SCHEMA:
        raise ValueError("reconcile_transaction_invalid")
    return _RootTransaction(
        transaction_id=value["transaction_id"],
        outputs_name=value["outputs_name"],
        parent_identity=_parse_identity(value["parent_identity"]),
        transaction_identity=_parse_identity(value["transaction_identity"]),
        journal_identity=_parse_identity(value["journal_identity"]),
        live_identity=_parse_identity_or_none(value["live_identity"]),
        staged_identity=_parse_identity(value["staged_identity"]),
        previous_identity=_parse_identity_or_none(value["previous_identity"]),
        approval_digest=value["approval_digest"],
        legacy_manifest=value["legacy_manifest"],
        phase=value["phase"],
    )


def _validate_transition(
    previous: _RootTransaction,
    current: _RootTransaction,
) -> None:
    if (previous.phase, current.phase) not in _ROOT_TRANSITIONS:
        raise ValueError("reconcile_transaction_phase_invalid")
    unchanged_previous_identity = previous.previous_identity
    if current.phase == "previous_moved":
        if current.previous_identity != current.live_identity:
            raise ValueError("reconcile_transaction_previous_invalid")
    elif current.previous_identity != unchanged_previous_identity:
        raise ValueError("reconcile_transaction_previous_invalid")
    if replace(
        current,
        phase=previous.phase,
        previous_identity=previous.previous_identity,
    ) != previous:
        raise ValueError("reconcile_transaction_authority_changed")


def _load_root_transaction(
    transaction_root: Path,
    *,
    expected_outputs_name: str,
) -> tuple[_JournalState, Path]:
    require_plain_directory(transaction_root)
    allowed = {_ROOT_JOURNAL_NAME, "lease.lock", "staged", "previous"}
    entries = _plain_scandir(transaction_root)
    names = {entry.name for entry in entries}
    if _ROOT_JOURNAL_NAME not in names or not names.issubset(allowed):
        raise ValueError("reconcile_transaction_invalid")
    journal_path = transaction_root / _ROOT_JOURNAL_NAME
    journal_status = plain_file_status(journal_path)
    maximum = _ROOT_JOURNAL_RECORD_LIMIT * (_ROOT_JOURNAL_GENERATION_LIMIT + 1)
    if journal_status.st_size > maximum:
        raise ValueError("reconcile_transaction_journal_overflow")
    raw = read_file_no_follow(
        journal_path,
        expected_status=journal_status,
        maximum_size=maximum,
    )
    state = _parse_root_journal(raw)
    transaction = state.transaction
    expected_cleanup_name = f"{_ROOT_CLEANUP_PREFIX}{transaction.transaction_id}"
    expected_prepare_name = f"{_ROOT_PREPARE_PREFIX}{transaction.transaction_id}"
    if transaction_root.name not in {
        _ROOT_TRANSACTION_NAME,
        expected_cleanup_name,
        expected_prepare_name,
    }:
        raise ValueError("reconcile_transaction_name_invalid")
    if path_identity_from_status(journal_status) != transaction.journal_identity:
        raise ValueError("reconcile_transaction_journal_identity_changed")
    _validate_root_transaction_document(
        transaction,
        transaction_root=transaction_root,
        expected_outputs_name=expected_outputs_name,
    )
    return state, journal_path


def _validate_root_transaction_document(
    transaction: _RootTransaction,
    *,
    transaction_root: Path,
    expected_outputs_name: str,
) -> None:
    if (
        not isinstance(transaction.transaction_id, str)
        or re.fullmatch(r"[0-9a-f]{32}", transaction.transaction_id) is None
        or transaction.outputs_name != expected_outputs_name
        or transaction.phase not in _ROOT_TRANSACTION_PHASES
        or transaction.transaction_identity != path_identity(transaction_root)
        or not isinstance(transaction.legacy_manifest, Mapping)
        or (
            transaction.approval_digest is not None
            and (
                not isinstance(transaction.approval_digest, str)
                or not _SHA256_RE.fullmatch(transaction.approval_digest)
            )
        )
    ):
        raise ValueError("reconcile_transaction_invalid")
    manifest_bytes = _canonical_json_bytes(transaction.legacy_manifest)
    manifest_digest = f"sha256:{sha256(manifest_bytes).hexdigest()}"
    manifest_entries = transaction.legacy_manifest.get("entries")
    manifest_parent = _parse_identity(
        transaction.legacy_manifest.get("parent_identity")
    )
    manifest_live = _parse_identity_or_none(
        transaction.legacy_manifest.get("outputs_identity")
    )
    if (
        not isinstance(manifest_entries, list)
        or bool(manifest_entries)
        != (transaction.approval_digest == manifest_digest)
        or manifest_parent != transaction.parent_identity
        or manifest_live != transaction.live_identity
        or (
            transaction.phase
            in {"building", "staged_ready", "aborting", "aborted"}
            and transaction.previous_identity is not None
        )
        or (
            transaction.phase
            in {"previous_moved", "live_committed", "terminal"}
            and transaction.previous_identity != transaction.live_identity
        )
    ):
        raise ValueError("reconcile_transaction_invalid")
    _manifest_entries_at(
        transaction.legacy_manifest,
        transaction_root / "previous",
        expected_outputs_name=expected_outputs_name,
    )


def _locate_root_coordinator(parent: Path) -> Path | None:
    active: Path | None = None
    cleanup: Path | None = None
    prepare: Path | None = None
    for entry in _plain_scandir(parent):
        name = entry.name
        if not name.startswith(".hsconfig-output-reconcile-"):
            continue
        path = parent / name
        if name == _ROOT_TRANSACTION_NAME:
            if active is not None:
                raise ValueError("reconcile_transaction_multiple")
            active = path
        elif re.fullmatch(
            re.escape(_ROOT_CLEANUP_PREFIX) + r"[0-9a-f]{32}",
            name,
        ):
            _require_plain_directory(path)
            cleanup_names = {child.name for child in _plain_scandir(path)}
            if not cleanup_names:
                continue
            if (
                _ROOT_JOURNAL_NAME not in cleanup_names
                or not cleanup_names.issubset({_ROOT_JOURNAL_NAME, "lease.lock"})
            ):
                raise ValueError("reconcile_cleanup_residue")
            if cleanup is not None:
                raise ValueError("reconcile_cleanup_multiple")
            cleanup = path
        elif re.fullmatch(
            re.escape(_ROOT_PREPARE_PREFIX) + r"[0-9a-f]{32}",
            name,
        ):
            _require_plain_directory(path)
            prepare_names = {child.name for child in _plain_scandir(path)}
            if not prepare_names:
                continue
            if (
                _ROOT_JOURNAL_NAME not in prepare_names
                or not prepare_names.issubset(
                    {_ROOT_JOURNAL_NAME, "lease.lock", "staged"}
                )
            ):
                raise ValueError("reconcile_prepare_residue")
            if prepare is not None:
                raise ValueError("reconcile_prepare_multiple")
            prepare = path
        else:
            raise ValueError("reconcile_coordinator_foreign")
    coordinators = [
        coordinator
        for coordinator in (active, cleanup, prepare)
        if coordinator is not None
    ]
    if len(coordinators) > 1:
        raise ValueError("reconcile_coordinator_multiple")
    return coordinators[0] if coordinators else None


def _require_recovery_approval(
    transaction: _RootTransaction,
    supplied_digest: str | None,
) -> None:
    expected = transaction.approval_digest
    if expected is None:
        if supplied_digest is not None:
            manifest_digest = (
                f"sha256:{sha256(_canonical_json_bytes(transaction.legacy_manifest)).hexdigest()}"
            )
            if supplied_digest != manifest_digest:
                raise ValueError("reconcile_legacy_approval_mismatch")
        return
    if supplied_digest is None:
        raise ValueError("reconcile_legacy_approval_required")
    if supplied_digest != expected:
        raise ValueError("reconcile_legacy_approval_mismatch")


def _reconstruct_root_phase(
    root: Path,
    transaction_root: Path,
    transaction: _RootTransaction,
    authority: _CatalogAuthority,
) -> str:
    live = _path_identity_or_none(root)
    staged = _path_identity_or_none(transaction_root / "staged")
    previous = _path_identity_or_none(transaction_root / "previous")
    old = transaction.live_identity
    new = transaction.staged_identity
    old_at_live = live == old if old is not None else live is None
    old_at_previous = previous == old if old is not None else previous is None

    if transaction.phase == "aborted":
        if old_at_live and staged is None and previous is None:
            return "aborted"
        raise ValueError("reconcile_transaction_physical_state_invalid")
    if transaction.phase == "aborting":
        if (
            old_at_live
            and staged in {new, None}
            and previous is None
        ):
            return "aborting"
        raise ValueError("reconcile_transaction_physical_state_invalid")
    if transaction.phase == "terminal":
        if live == new and staged is None and previous is None:
            return "terminal"
        raise ValueError("reconcile_transaction_physical_state_invalid")
    if transaction.phase == "building":
        if old_at_live and staged == new and previous is None:
            try:
                staged_inventory = _scan_inventory(
                    transaction_root / "staged",
                    authority,
                    expected_root_identity=new,
                )
            except (OSError, ValueError):
                return "building"
            if _inventory_is_current(staged_inventory):
                return "staged_ready"
            return "building"
        raise ValueError("reconcile_transaction_physical_state_invalid")
    if transaction.phase == "staged_ready":
        if old_at_live and staged == new and previous is None:
            return "staged_ready"
        if live is None and staged == new and old_at_previous:
            return "previous_moved"
        if live == new and staged is None and (
            old_at_previous or previous is None
        ):
            return "live_committed" if previous is not None else "terminal"
        raise ValueError("reconcile_transaction_physical_state_invalid")
    if transaction.phase == "previous_moved":
        if live is None and staged == new and old_at_previous:
            return "previous_moved"
        if live == new and staged is None and (
            old_at_previous or previous is None
        ):
            return "live_committed" if previous is not None else "terminal"
        raise ValueError("reconcile_transaction_physical_state_invalid")
    if transaction.phase == "live_committed":
        if live == new and staged is None and (
            old_at_previous or previous is None
        ):
            return "live_committed" if previous is not None else "terminal"
        raise ValueError("reconcile_transaction_physical_state_invalid")
    raise ValueError("reconcile_transaction_phase_invalid")


def _append_inferred_transitions(
    journal_path: Path,
    state: _JournalState,
    target_phase: str,
    *,
    fault_hook: FaultHook,
) -> _JournalState:
    order = ("staged_ready", "previous_moved", "live_committed", "terminal")
    if state.transaction.phase == "building":
        if target_phase == "building":
            return state
        if target_phase != "staged_ready":
            raise ValueError("reconcile_transaction_phase_invalid")
        return _append_root_transition(
            journal_path,
            state,
            replace(state.transaction, phase="staged_ready"),
            fault_hook=fault_hook,
        )
    if state.transaction.phase in {"aborting", "aborted", "terminal"}:
        if state.transaction.phase != target_phase:
            raise ValueError("reconcile_transaction_phase_invalid")
        return state
    start = order.index(state.transaction.phase)
    target = order.index(target_phase)
    if target < start:
        raise ValueError("reconcile_transaction_phase_invalid")
    for phase in order[start + 1 : target + 1]:
        transaction = state.transaction
        if phase == "previous_moved":
            transaction = replace(
                transaction,
                previous_identity=transaction.live_identity,
                phase=phase,
            )
        else:
            transaction = replace(transaction, phase=phase)
        state = _append_root_transition(
            journal_path,
            state,
            transaction,
            fault_hook=fault_hook,
        )
    return state


def _publish_cleanup_tombstone(
    transaction_root: Path,
    transaction: _RootTransaction,
    *,
    fault_hook: FaultHook,
) -> Path:
    if transaction.phase not in {"terminal", "aborted"}:
        raise ValueError("reconcile_transaction_not_terminal")
    expected_name = f"{_ROOT_CLEANUP_PREFIX}{transaction.transaction_id}"
    tombstone = transaction_root.parent / expected_name
    if transaction_root.name == expected_name:
        return transaction_root
    if transaction_root.name != _ROOT_TRANSACTION_NAME:
        raise ValueError("reconcile_cleanup_name_invalid")
    secure_replace(
        transaction_root,
        tombstone,
        expected_source_identity=transaction.transaction_identity,
        expected_source_parent_identity=transaction.parent_identity,
        expected_target_parent_identity=transaction.parent_identity,
        expected_target_absent=True,
    )
    fault_hook("after_cleanup_tombstone_publish")
    return tombstone


def _cleanup_tombstone(
    tombstone: Path,
    state: _JournalState,
    *,
    fault_hook: FaultHook,
) -> None:
    transaction = state.transaction
    expected_name = f"{_ROOT_CLEANUP_PREFIX}{transaction.transaction_id}"
    if tombstone.name != expected_name:
        raise ValueError("reconcile_cleanup_name_invalid")
    journal_path = tombstone / _ROOT_JOURNAL_NAME
    lease_path = tombstone / "lease.lock"
    allow_cleanup_lease_create = _journal_only_cleanup_lock_may_create(
        tombstone,
        state,
        journal_path,
    )
    tombstone_guard = _capture_expected_directory_guard(
        tombstone,
        transaction.transaction_identity,
    )
    with ExclusiveFileLock(
        lease_path,
        timeout_seconds=0,
        expected_parent_identity=transaction.transaction_identity,
        path_guard=tombstone_guard,
        create_if_missing=allow_cleanup_lease_create,
    ):
        if path_identity(tombstone) != transaction.transaction_identity:
            raise ValueError("reconcile_transaction_identity_changed")
        names = {entry.name for entry in _plain_scandir(tombstone)}
        if names != {_ROOT_JOURNAL_NAME, "lease.lock"}:
            raise ValueError("reconcile_transaction_cleanup_invalid")
        journal_status = plain_file_status(journal_path)
        if path_identity_from_status(journal_status) != transaction.journal_identity:
            raise ValueError("reconcile_transaction_journal_identity_changed")
        lease_identity = path_identity(lease_path)
    secure_unlink(
        lease_path,
        expected_identity=lease_identity,
        expected_parent_identity=transaction.transaction_identity,
    )
    fault_hook("after_cleanup_tombstone_lease_unlink")
    secure_unlink(
        journal_path,
        expected_identity=transaction.journal_identity,
        expected_parent_identity=transaction.transaction_identity,
    )
    fault_hook("after_cleanup_tombstone_journal_unlink")
    fault_hook("before_cleanup_tombstone_rmdir")
    secure_rmdir(
        tombstone,
        expected_identity=transaction.transaction_identity,
        expected_parent_identity=transaction.parent_identity,
    )
    fault_hook("after_cleanup_tombstone_rmdir")


def _capture_expected_directory_guard(
    path: Path,
    expected_identity: tuple[int, int, int],
) -> FilesystemPathGuard:
    guard = capture_plain_ancestor_guard(path)
    if (
        not guard.rows
        or guard.rows[-1][0] != path
        or guard.rows[-1][1] != expected_identity
    ):
        raise ValueError("filesystem_path_identity_changed")
    return guard


def _journal_only_cleanup_lock_may_create(
    coordinator: Path,
    state: _JournalState,
    journal_path: Path,
) -> bool:
    transaction = state.transaction
    expected_name = f"{_ROOT_CLEANUP_PREFIX}{transaction.transaction_id}"
    if coordinator.name != expected_name:
        return False
    names = {entry.name for entry in _plain_scandir(coordinator)}
    if (
        transaction.phase not in {"terminal", "aborted"}
        or path_identity(coordinator) != transaction.transaction_identity
        or journal_path != coordinator / _ROOT_JOURNAL_NAME
        or path_identity(journal_path) != transaction.journal_identity
        or names not in (
            {_ROOT_JOURNAL_NAME},
            {_ROOT_JOURNAL_NAME, "lease.lock"},
        )
    ):
        raise ValueError("reconcile_transaction_cleanup_invalid")
    return names == {_ROOT_JOURNAL_NAME}


def _validate_root_transaction_authority(
    transaction: _RootTransaction,
    authority: _CatalogAuthority,
) -> None:
    entries = _manifest_entries_at(
        transaction.legacy_manifest,
        Path(transaction.outputs_name),
        expected_outputs_name=transaction.outputs_name,
    )
    if any(entry.deck_name not in authority.names for entry in entries):
        raise ValueError("reconcile_transaction_legacy_authority_invalid")


def _require_staged_authority(
    staged_root: Path,
    transaction: _RootTransaction,
    authority: _CatalogAuthority,
) -> None:
    if path_identity(staged_root) != transaction.staged_identity:
        raise ValueError("reconcile_transaction_staged_identity_invalid")
    if not _inventory_is_current(
        _scan_inventory(
            staged_root,
            authority,
            expected_root_identity=transaction.staged_identity,
        )
    ):
        raise ValueError("reconcile_staged_inventory_invalid")


def _require_approval_manifest_current(
    root: Path,
    transaction: _RootTransaction,
) -> None:
    candidate = root
    if not os.path.lexists(candidate):
        previous = root.parent / _ROOT_TRANSACTION_NAME / "previous"
        if (
            transaction.live_identity is not None
            and _path_identity_or_none(previous) == transaction.live_identity
        ):
            candidate = previous
    if transaction.live_identity is None:
        if os.path.lexists(candidate):
            raise ValueError("reconcile_output_root_changed")
        return
    if _path_identity_or_none(candidate) != transaction.live_identity:
        raise ValueError("reconcile_output_root_changed")
    entries = _manifest_entries_at(
        transaction.legacy_manifest,
        candidate,
        expected_outputs_name=transaction.outputs_name,
    )
    _require_deletion_manifest_unchanged(candidate, entries)


def _remove_approved_previous(
    previous_root: Path,
    transaction: _RootTransaction,
    *,
    fault_hook: FaultHook,
) -> None:
    if transaction.previous_identity is None:
        if os.path.lexists(previous_root):
            raise ValueError("reconcile_transaction_previous_invalid")
        return
    if not os.path.lexists(previous_root):
        return
    if path_identity(previous_root) != transaction.previous_identity:
        raise ValueError("reconcile_deletion_identity_changed")
    entries = _manifest_entries_at(
        transaction.legacy_manifest,
        previous_root,
        expected_outputs_name=transaction.outputs_name,
    )
    expected_names = {entry.relative_root for entry in entries}
    actual_names = {entry.name for entry in _plain_scandir(previous_root)}
    if not actual_names.issubset(expected_names):
        raise ValueError("reconcile_deletion_identity_changed")
    for entry in entries:
        if not os.path.lexists(entry.path):
            continue
        _remove_manifest_entry(
            entry,
            expected_parent_identity=transaction.previous_identity,
            fault_hook=fault_hook,
        )
    if _plain_scandir(previous_root):
        raise ValueError("reconcile_obsolete_output_cleanup_incomplete")
    secure_rmdir(
        previous_root,
        expected_identity=transaction.previous_identity,
        expected_parent_identity=transaction.transaction_identity,
    )


def _remove_process_owned_tree(
    root: Path,
    *,
    expected_identity: tuple[int, int, int],
    expected_parent_identity: tuple[int, int, int],
    fault_hook: FaultHook = no_fault,
) -> None:
    if not os.path.lexists(root):
        return
    nodes = _capture_plain_tree(root)
    entry = _DeletionEntry(
        path=root,
        relative_root=root.name,
        identity=expected_identity,
        deck_name="process-owned-staging",
        nodes=nodes,
        tree_sha256=_tree_content_sha256(nodes),
    )
    _remove_manifest_entry(
        entry,
        expected_parent_identity=expected_parent_identity,
        fault_hook=lambda stage: (
            fault_hook("during_abort_staging_cleanup")
            if stage == "during_previous_cleanup"
            else None
        ),
    )


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _identity_json(
    value: tuple[int, int, int] | None,
) -> list[int] | None:
    return list(value) if value is not None else None


def _parse_identity(value: Any) -> tuple[int, int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(item) is not int or item < 0 for item in value)
    ):
        raise ValueError("reconcile_identity_invalid")
    return value[0], value[1], value[2]


def _parse_identity_or_none(
    value: Any,
) -> tuple[int, int, int] | None:
    return None if value is None else _parse_identity(value)


def _path_identity_or_none(path: Path) -> tuple[int, int, int] | None:
    try:
        return path_identity(path)
    except FileNotFoundError:
        return None


def _scan_inventory(
    outputs_root: Path,
    authority: _CatalogAuthority,
    *,
    expected_root_identity: tuple[int, int, int] | None = None,
) -> OutputInventory:
    context = (
        ScanContext.identity_bound_staging(expected_root_identity)
        if expected_root_identity is not None
        else ScanContext(include_sibling_coordinators=False)
    )
    return _scan_inventory_with_context(
        Path(outputs_root),
        authority,
        context=context,
    )


def _scan_public_inventory(
    outputs_root: Path,
    authority: _CatalogAuthority,
) -> OutputInventory:
    return _scan_inventory_with_context(
        Path(outputs_root),
        authority,
        context=ScanContext(),
    )


def _capture_deletion_manifest(
    outputs_root: Path,
    authority: _CatalogAuthority,
) -> tuple[_DeletionEntry, ...]:
    root = Path(os.path.abspath(outputs_root))
    if not os.path.lexists(root):
        return ()
    _require_plain_directory(root)
    expected = set(authority.names)
    entries: list[_DeletionEntry] = []
    casefold_names: set[str] = set()
    for child in _plain_scandir(root):
        if child.name.casefold() in casefold_names:
            raise ValueError("reconcile_output_case_alias")
        casefold_names.add(child.name.casefold())
        path = root / child.name
        _require_plain_directory(path)
        identity = path_identity_from_status(os.lstat(path))
        if child.name in expected:
            deck_name = child.name
            child_names = {entry.name for entry in _plain_scandir(path)}
            if child_names.issubset(CANONICAL_DECK_LAYOUT):
                _validate_canonical_deck_root(
                    path,
                    deck_name=deck_name,
                    deck_fingerprint=authority.fingerprints[deck_name],
                )
            else:
                try:
                    legacy_name = _legacy_deck_identity(path, authority)
                except ValueError as error:
                    raise ValueError(
                        "reconcile_unexpected_stable_output_entry"
                    ) from error
                if legacy_name != child.name:
                    raise ValueError(
                        "reconcile_unexpected_stable_output_entry"
                    )
        elif child.name.casefold() in {
            name.casefold() for name in authority.names
        }:
            raise ValueError("reconcile_output_case_alias")
        else:
            deck_name = _legacy_deck_identity(path, authority)
        nodes = _capture_plain_tree(path)
        entries.append(
            _DeletionEntry(
                path=path,
                relative_root=child.name,
                identity=identity,
                deck_name=deck_name,
                nodes=nodes,
                tree_sha256=_tree_content_sha256(nodes),
            )
        )
    return tuple(sorted(entries, key=lambda entry: entry.path.name.casefold()))


def _validate_canonical_deck_root(
    root: Path,
    *,
    deck_name: str,
    deck_fingerprint: str,
) -> None:
    with lease_package_input(root) as lease:
        publication = lease.publication
        if (
            publication is None
            or publication.deck_name != deck_name
            or publication.deck_fingerprint != deck_fingerprint
            or publication.content_root_sha256 != lease.content_root_sha256
        ):
            raise ValueError("reconcile_canonical_output_invalid")
        validate_finalized_publication_authority(root, publication)
    revisions = root / "revisions"
    revision_names = tuple(_plain_scandir(revisions))
    if len(revision_names) != 1:
        raise ValueError("reconcile_canonical_output_invalid")
    revision = revision_names[0]
    if not REVISION_NAME_RE.fullmatch(revision.name):
        raise ValueError("reconcile_canonical_output_invalid")
    verified = snapshot_and_verify_revision(revisions / revision.name)
    if (
        revision.name != "sha256-" + verified.manifest.content_root_sha256
        or verified.manifest.deck_name != deck_name
        or verified.manifest.deck_fingerprint != deck_fingerprint
    ):
        raise ValueError("reconcile_canonical_output_invalid")


def _tree_content_sha256(nodes: Sequence[_TreeNode]) -> str:
    payload = [
        {
            "relative_path": node.relative_path,
            "node_type": node.node_type,
            "size": node.size,
            "content_sha256": node.content_sha256,
        }
        for node in nodes
    ]
    return f"sha256:{sha256(_canonical_json_bytes(payload)).hexdigest()}"


def _deletion_manifest_document(
    outputs_root: Path,
    entries: Sequence[_DeletionEntry],
) -> dict[str, Any]:
    root = Path(os.path.abspath(outputs_root))
    parent_identity = path_identity(root.parent)
    root_identity = path_identity(root) if os.path.lexists(root) else None
    return {
        "schema_version": _APPROVAL_SCHEMA,
        "outputs_name": root.name,
        "parent_identity": list(parent_identity),
        "outputs_identity": (
            list(root_identity) if root_identity is not None else None
        ),
        "entries": [
            {
                "relative_root": entry.relative_root,
                "deck_name": entry.deck_name,
                "root_identity": list(entry.identity),
                "tree_sha256": entry.tree_sha256,
                "nodes": [
                    {
                        "relative_path": node.relative_path,
                        "identity": list(node.identity),
                        "node_type": node.node_type,
                        "size": node.size,
                        "content_sha256": node.content_sha256,
                    }
                    for node in entry.nodes
                ],
            }
            for entry in entries
        ],
    }


def _manifest_entries_at(
    manifest: Mapping[str, Any],
    root: Path,
    *,
    expected_outputs_name: str | None = None,
) -> tuple[_DeletionEntry, ...]:
    if expected_outputs_name is None:
        expected_outputs_name = root.name
    if (
        set(manifest)
        != {
            "schema_version",
            "outputs_name",
            "parent_identity",
            "outputs_identity",
            "entries",
        }
        or manifest.get("schema_version") != _APPROVAL_SCHEMA
        or manifest.get("outputs_name") != expected_outputs_name
        or not isinstance(manifest.get("entries"), list)
    ):
        raise ValueError("reconcile_legacy_manifest_invalid")
    entries: list[_DeletionEntry] = []
    for value in manifest["entries"]:
        if not isinstance(value, Mapping) or set(value) != {
            "relative_root",
            "deck_name",
            "root_identity",
            "tree_sha256",
            "nodes",
        }:
            raise ValueError("reconcile_legacy_manifest_invalid")
        relative_root = value["relative_root"]
        if (
            not isinstance(relative_root, str)
            or Path(relative_root).name != relative_root
            or not isinstance(value["deck_name"], str)
            or not _SHA256_RE.fullmatch(str(value["tree_sha256"]))
            or not isinstance(value["nodes"], list)
        ):
            raise ValueError("reconcile_legacy_manifest_invalid")
        nodes: list[_TreeNode] = []
        for node in value["nodes"]:
            if not isinstance(node, Mapping) or set(node) != {
                "relative_path",
                "identity",
                "node_type",
                "size",
                "content_sha256",
            }:
                raise ValueError("reconcile_legacy_manifest_invalid")
            relative_path = node["relative_path"]
            node_type = node["node_type"]
            content_sha256 = node["content_sha256"]
            if (
                not isinstance(relative_path, str)
                or Path(relative_path).is_absolute()
                or ".." in Path(relative_path).parts
                or node_type not in {"file", "directory"}
                or type(node["size"]) is not int
                or node["size"] < 0
                or (
                    node_type == "file"
                    and (
                        not isinstance(content_sha256, str)
                        or not _SHA256_RE.fullmatch(content_sha256)
                    )
                )
                or (node_type == "directory" and content_sha256 is not None)
            ):
                raise ValueError("reconcile_legacy_manifest_invalid")
            nodes.append(
                _TreeNode(
                    relative_path=relative_path,
                    identity=_parse_identity(node["identity"]),
                    node_type=node_type,
                    size=node["size"],
                    content_sha256=content_sha256,
                )
            )
        entry = _DeletionEntry(
            path=root / relative_root,
            relative_root=relative_root,
            identity=_parse_identity(value["root_identity"]),
            deck_name=value["deck_name"],
            nodes=tuple(nodes),
            tree_sha256=value["tree_sha256"],
        )
        if _tree_content_sha256(entry.nodes) != entry.tree_sha256:
            raise ValueError("reconcile_legacy_manifest_invalid")
        entries.append(entry)
    if tuple(sorted(row.relative_root.casefold() for row in entries)) != tuple(
        row.relative_root.casefold() for row in entries
    ) or len({row.relative_root.casefold() for row in entries}) != len(entries):
        raise ValueError("reconcile_legacy_manifest_invalid")
    return tuple(entries)


def _manifest_parent_identity(
    entry: _DeletionEntry,
    node: _TreeNode,
) -> tuple[int, int, int]:
    parent = Path(node.relative_path).parent.as_posix()
    if parent == ".":
        return entry.identity
    matches = [
        candidate.identity
        for candidate in entry.nodes
        if candidate.relative_path == parent
        and candidate.node_type == "directory"
    ]
    if len(matches) != 1:
        raise ValueError("reconcile_legacy_manifest_invalid")
    return matches[0]


def _legacy_deck_identity(
    root: Path,
    authority: _CatalogAuthority,
) -> str:
    names = {entry.name for entry in _plain_scandir(root)}
    if not (
        names
        and (
            names.issubset(_LEGACY_CONFIGURE_LAYOUT)
            or names.issubset(_LEGACY_PACKAGE_LAYOUT)
        )
    ):
        raise ValueError(f"reconcile_unknown_output_root:{root.name}")
    candidates = (
        root / "04_package" / "reports" / "input_manifest.json",
        root / "reports" / "input_manifest.json",
    )
    identities: set[str] = set()
    for path in candidates:
        if not os.path.lexists(path):
            continue
        payload = _read_plain_json(path)
        name = payload.get("deck_name") if isinstance(payload, Mapping) else None
        if isinstance(name, str) and name in authority.names:
            identities.add(name)
    if len(identities) != 1:
        raise ValueError(f"reconcile_unknown_output_root:{root.name}")
    return identities.pop()


def _capture_plain_tree(root: Path) -> tuple[_TreeNode, ...]:
    guard = capture_plain_ancestor_guard(root)
    root_identity = path_identity(root)
    rows: list[_TreeNode] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        for entry in _plain_scandir(directory):
            path = directory / entry.name
            node_stat = os.lstat(path)
            if _status_is_reparse(node_stat):
                raise ValueError("reconcile_deletion_reparse")
            relative = path.relative_to(root).as_posix()
            if stat.S_ISDIR(node_stat.st_mode):
                pending.append(path)
                node_type = "directory"
                content_sha256 = None
            elif stat.S_ISREG(node_stat.st_mode):
                if node_stat.st_nlink != 1:
                    raise ValueError("reconcile_deletion_hardlink")
                node_type = "file"
                content = read_file_no_follow(
                    path,
                    expected_status=node_stat,
                    maximum_size=max(node_stat.st_size, 1),
                )
                content_sha256 = f"sha256:{sha256(content).hexdigest()}"
            else:
                raise ValueError("reconcile_deletion_node_invalid")
            rows.append(
                _TreeNode(
                    relative_path=relative,
                    identity=path_identity_from_status(node_stat),
                    node_type=node_type,
                    size=node_stat.st_size,
                    content_sha256=content_sha256,
                )
            )
    result = tuple(sorted(rows, key=lambda row: row.relative_path))
    guard.validate()
    if path_identity(root) != root_identity:
        raise ValueError("reconcile_deletion_identity_changed")
    return result


def _require_deletion_manifest_unchanged(
    outputs_root: Path,
    manifest: Sequence[_DeletionEntry],
) -> None:
    root = Path(os.path.abspath(outputs_root))
    if not manifest:
        if os.path.lexists(root) and _plain_scandir(root):
            raise ValueError("reconcile_output_root_changed")
        return
    actual_names = tuple(entry.name for entry in _plain_scandir(root))
    expected_names = tuple(entry.path.name for entry in manifest)
    if tuple(sorted(actual_names, key=str.casefold)) != expected_names:
        raise ValueError("reconcile_output_root_changed")
    for entry in manifest:
        current = os.lstat(entry.path)
        if (
            _status_is_reparse(current)
            or not stat.S_ISDIR(current.st_mode)
            or path_identity_from_status(current) != entry.identity
            or _capture_plain_tree(entry.path) != entry.nodes
        ):
            raise ValueError("reconcile_deletion_identity_changed")


def _remove_deletion_manifest(
    outputs_root: Path,
    manifest: Sequence[_DeletionEntry],
) -> None:
    _require_deletion_manifest_unchanged(outputs_root, manifest)
    for entry in manifest:
        _remove_manifest_entry(entry)
    root = Path(os.path.abspath(outputs_root))
    if os.path.lexists(root) and _plain_scandir(root):
        raise ValueError("reconcile_obsolete_output_cleanup_incomplete")


def _remove_manifest_entry(
    entry: _DeletionEntry,
    *,
    expected_parent_identity: tuple[int, int, int] | None = None,
    fault_hook: FaultHook = no_fault,
) -> None:
    current = os.lstat(entry.path)
    if path_identity_from_status(current) != entry.identity:
        raise ValueError("reconcile_deletion_identity_changed")
    for node in reversed(entry.nodes):
        path = entry.path / Path(node.relative_path)
        try:
            current = os.lstat(path)
        except FileNotFoundError:
            continue
        if path_identity_from_status(current) != node.identity:
            raise ValueError("reconcile_deletion_identity_changed")
        parent_identity = _manifest_parent_identity(entry, node)
        if node.node_type == "directory":
            secure_rmdir(
                path,
                expected_identity=node.identity,
                expected_parent_identity=parent_identity,
            )
        else:
            secure_unlink(
                path,
                expected_identity=node.identity,
                expected_parent_identity=parent_identity,
            )
        fault_hook("during_previous_cleanup")
    secure_rmdir(
        entry.path,
        expected_identity=entry.identity,
        expected_parent_identity=(
            expected_parent_identity
            if expected_parent_identity is not None
            else path_identity(entry.path.parent)
        ),
    )


def _build_rendered_audited_runs(
    authority: _CatalogAuthority,
) -> dict[str, RenderedConfigureRun]:
    """Build from the frozen audited request authority, never old outputs."""

    result = dict(render_all_audited_configure_runs(authority.catalog_path))
    if tuple(result) != authority.names:
        raise ValueError("reconcile_rendered_deck_set_invalid")
    return result


def _require_complete_rendered_set(
    rendered: Mapping[str, RenderedConfigureRun],
    authority: _CatalogAuthority,
) -> None:
    if tuple(rendered) != authority.names:
        raise ValueError("reconcile_rendered_deck_set_invalid")
    for deck_name in authority.names:
        run = rendered[deck_name]
        if (
            not isinstance(run, RenderedConfigureRun)
            or run.model.deck_name != deck_name
            or run.model.deck_fingerprint != authority.fingerprints[deck_name]
            or render_configure_run_model(run.model) != run
        ):
            raise ValueError("reconcile_rendered_output_invalid")


def _read_plain_json(path: Path) -> Any:
    node_stat = os.lstat(path)
    if (
        _status_is_reparse(node_stat)
        or not stat.S_ISREG(node_stat.st_mode)
        or node_stat.st_nlink != 1
    ):
        raise ValueError("reconcile_json_file_unsafe")
    try:
        return json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("reconcile_json_invalid") from error


def _plain_scandir(path: Path) -> tuple[os.DirEntry[str], ...]:
    try:
        with os.scandir(path) as iterator:
            rows = tuple(iterator)
    except OSError as error:
        raise ValueError("reconcile_directory_unreadable") from error
    if len({row.name.casefold() for row in rows}) != len(rows):
        raise ValueError("reconcile_path_case_alias")
    return tuple(sorted(rows, key=lambda row: (row.name.casefold(), row.name)))


def _require_plain_directory(path: Path) -> None:
    try:
        node_stat = os.lstat(path)
    except OSError as error:
        raise ValueError("reconcile_directory_missing") from error
    if _status_is_reparse(node_stat) or not stat.S_ISDIR(node_stat.st_mode):
        raise ValueError("reconcile_directory_unsafe")


def _status_is_reparse(node_stat: os.stat_result) -> bool:
    return bool(
        stat.S_ISLNK(node_stat.st_mode)
        or getattr(node_stat, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


build_rendered_audited_runs = _build_rendered_audited_runs
