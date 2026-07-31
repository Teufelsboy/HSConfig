"""Crash-recoverable publication of one immutable configure-run revision."""

from __future__ import annotations

import json
import os
import re
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from hsconfig.atomic_io import (
    ExclusiveFileLock,
    FaultHook,
    no_fault,
)
from hsconfig.configure_run_model import (
    RenderedConfigureRun,
)
from hsconfig.current_output import (
    CURRENT_PATH,
    CURRENT_SCHEMA_VERSION,
    OutputPublication,
    output_publication_bytes,
    parse_output_publication,
    resolve_current_publication_unlocked,
    snapshot_and_verify_revision,
)
from hsconfig.package_io import (
    MAX_FILESYSTEM_DIRECTORIES,
    MAX_FILESYSTEM_DEPTH,
    MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY,
    MAX_FILESYSTEM_NODES,
    MAX_RUN_PATH_BYTES,
    FilesystemPathGuard,
    capture_plain_ancestor_guard,
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
    status_is_reparse,
)
from hsconfig.package_domain import canonical_relative_path


_TRANSACTION_SCHEMA_VERSION = 1
_MAX_TRANSACTION_FILES = 256
_MAX_TRANSACTION_BYTES = 16 * 1024 * 1024
_MAX_TRANSACTION_FILE_BYTES = 1024 * 1024
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
_REVISION_NAME = re.compile(r"^sha256-[0-9a-f]{64}$")
_STAGING_NAME = re.compile(r"^\.staging-[0-9a-f]{32}$")
_PHASES = frozenset(
    {
        "prepared",
        "staging_owned",
        "staging_verified",
        "revision_ready",
        "pointer_committed",
        "cleanup_started",
        "finalized",
    }
)
_JOURNAL_KEYS = frozenset(
    {
        "schema_version",
        "transaction_id",
        "deck_name",
        "deck_fingerprint",
        "content_root_sha256",
        "staging",
        "revision",
        "previous_revision",
        "previous_revision_identity",
        "previous_owner_transaction_id",
        "staging_identity",
        "revision_identity",
        "owns_revision",
        "phase",
    }
)


@dataclass(frozen=True, slots=True)
class PublishedOutput:
    output_root: Path
    revision_root: Path
    package_root: Path
    content_root_sha256: str
    reused_existing_revision: bool


@dataclass(frozen=True, slots=True)
class _PointerSnapshot:
    existed: bool
    content: bytes | None
    identity: tuple[int, int, int, int, int, int] | None


@dataclass(frozen=True, slots=True)
class _Transaction:
    schema_version: int
    transaction_id: str
    deck_name: str
    deck_fingerprint: str
    content_root_sha256: str
    staging: str
    revision: str
    previous_revision: str | None
    previous_revision_identity: tuple[int, int, int] | None
    previous_owner_transaction_id: str | None
    staging_identity: tuple[int, int, int] | None
    revision_identity: tuple[int, int, int] | None
    owns_revision: bool
    phase: str

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != _TRANSACTION_SCHEMA_VERSION
            or not _TRANSACTION_ID.fullmatch(self.transaction_id)
            or not self.deck_name
            or self.deck_name != self.deck_name.strip()
            or not _is_sha256(self.deck_fingerprint)
            or not _is_sha256(self.content_root_sha256)
            or self.staging
            != f"revisions/.staging-{self.transaction_id}"
            or self.revision
            != f"revisions/sha256-{self.content_root_sha256}"
            or (
                self.previous_revision is not None
                and not _canonical_revision(self.previous_revision)
            )
            or not _identity_or_none(self.previous_revision_identity)
            or (
                self.previous_owner_transaction_id is not None
                and not _TRANSACTION_ID.fullmatch(
                    self.previous_owner_transaction_id
                )
            )
            or not _identity_or_none(self.staging_identity)
            or not _identity_or_none(self.revision_identity)
            or type(self.owns_revision) is not bool
            or self.phase not in _PHASES
            or not _valid_phase_state(self)
        ):
            raise ValueError("publisher_transaction_invalid")


def publish_configure_run(
    rendered: RenderedConfigureRun,
    output_root: Path,
    *,
    fault_hook: FaultHook = no_fault,
) -> PublishedOutput:
    """Publish a validated immutable run and atomically select it as current."""

    if not isinstance(rendered, RenderedConfigureRun):
        raise TypeError("rendered_configure_run_required")
    root = Path(output_root)
    ancestor_guard = capture_plain_ancestor_guard(root)
    if path_lexists(root):
        require_plain_directory(root)
        lock_candidate = root / ".publish.lock"
        if path_lexists(lock_candidate):
            plain_file_status(lock_candidate)
    _ensure_layout(root)
    layout_guards = _capture_layout_guards(root)
    with ExclusiveFileLock(root / ".publish.lock"):
        layout_guards = _capture_layout_guards(root)
        ancestor_guard.validate()
        _validate_layout_guards(layout_guards)
        fault_hook("after_lock")
        _validate_layout_guards(layout_guards)
        current = _reconcile_locked(root)
        if (
            current is not None
            and current.content_root_sha256
            == rendered.content_root_sha256
            and current.revision_root.name
            == f"sha256-{rendered.content_root_sha256}"
        ):
            _validate_layout_guards(layout_guards)
            return replace(current, reused_existing_revision=True)
        pointer_snapshot = _snapshot_pointer(root)
        transaction = _new_transaction(rendered, current)
        journal_path = _journal_path(root, transaction.transaction_id)
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )

        staging_root = root / transaction.staging
        staging_identity = secure_create_directory(
            staging_root,
            expected_parent_identity=path_identity(staging_root.parent),
        )
        _validate_layout_guards(layout_guards)
        if path_identity(staging_root) != staging_identity:
            raise ValueError("publication_staging_identity_mismatch")
        transaction = replace(
            transaction,
            staging_identity=staging_identity,
            phase="staging_owned",
        )
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )
        _write_rendered_run(rendered, staging_root)
        _validate_layout_guards(layout_guards)
        fault_hook("after_staging_render")
        _validate_layout_guards(layout_guards)
        staged = snapshot_and_verify_revision(staging_root)
        if (
            staged.manifest.content_root_sha256
            != rendered.content_root_sha256
            or staged.manifest.deck_name != rendered.model.deck_name
            or staged.manifest.deck_fingerprint
            != rendered.model.deck_fingerprint
        ):
            raise ValueError("staged_revision_identity_mismatch")
        transaction = replace(transaction, phase="staging_verified")
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )
        fault_hook("after_staging_verify")
        _validate_layout_guards(layout_guards)

        revision_root = root / transaction.revision
        reused = path_lexists(revision_root)
        if reused:
            require_plain_directory(revision_root)
            existing = snapshot_and_verify_revision(revision_root)
            if (
                existing.manifest.content_root_sha256
                != rendered.content_root_sha256
                or existing.manifest.deck_name != rendered.model.deck_name
                or existing.manifest.deck_fingerprint
                != rendered.model.deck_fingerprint
            ):
                raise ValueError("publication_digest_target_conflict")
            _remove_owned_tree(
                staging_root,
                expected_identity=staging_identity,
            )
            transaction = replace(
                transaction,
                staging_identity=None,
                revision_identity=path_identity(revision_root),
                owns_revision=False,
                phase="revision_ready",
            )
        else:
            _validate_layout_guards(layout_guards)
            revisions_identity = path_identity(staging_root.parent)
            secure_replace(
                staging_root,
                revision_root,
                expected_source_identity=staging_identity,
                expected_source_parent_identity=revisions_identity,
                expected_target_parent_identity=revisions_identity,
                expected_target_absent=True,
            )
            _validate_layout_guards(layout_guards)
            revision_identity = path_identity(revision_root)
            if revision_identity != staging_identity:
                raise ValueError("publication_revision_identity_mismatch")
            transaction = replace(
                transaction,
                staging_identity=None,
                revision_identity=revision_identity,
                owns_revision=True,
                phase="revision_ready",
            )
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )
        fault_hook("after_revision_rename")
        _validate_layout_guards(layout_guards)

        publication = OutputPublication(
            schema_version=CURRENT_SCHEMA_VERSION,
            deck_name=rendered.model.deck_name,
            deck_fingerprint=rendered.model.deck_fingerprint,
            revision=transaction.revision,
            content_root_sha256=rendered.content_root_sha256,
        )
        fault_hook("before_pointer_replace")
        _validate_layout_guards(layout_guards)
        _replace_pointer_if_unchanged(
            root,
            pointer_snapshot,
            output_publication_bytes(publication),
            transaction_id=transaction.transaction_id,
            fault_hook=fault_hook,
        )
        _validate_layout_guards(layout_guards)
        fault_hook("after_pointer_replace")
        _validate_layout_guards(layout_guards)
        transaction = replace(transaction, phase="pointer_committed")
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )

        selected, _verified = resolve_current_publication_unlocked(root)
        if selected != publication:
            raise ValueError("publication_pointer_verification_failed")
        fault_hook("before_old_revision_cleanup")
        _validate_layout_guards(layout_guards)
        _cleanup_after_commit(
            root,
            transaction,
            journal_path,
            fault_hook=fault_hook,
        )
        _validate_layout_guards(layout_guards)
        return PublishedOutput(
            output_root=root,
            revision_root=revision_root,
            package_root=revision_root / "04_package",
            content_root_sha256=rendered.content_root_sha256,
            reused_existing_revision=reused,
        )


def reconcile_output(output_root: Path) -> PublishedOutput | None:
    """Recover publisher-owned interrupted state and return verified current."""

    root = Path(output_root)
    if not path_lexists(root):
        return None
    ancestor_guard = capture_plain_ancestor_guard(root / ".publish.lock")
    _validate_existing_layout(root)
    layout_guards = _capture_layout_guards(root)
    with ExclusiveFileLock(root / ".publish.lock"):
        layout_guards = _capture_layout_guards(root)
        ancestor_guard.validate()
        _validate_layout_guards(layout_guards)
        result = _reconcile_locked(root)
        _validate_layout_guards(layout_guards)
        return result


def validate_finalized_publication_authority(
    output_root: Path,
    publication: OutputPublication,
) -> None:
    """Validate the one immutable owner journal without performing recovery."""

    if not isinstance(publication, OutputPublication):
        raise TypeError("output_publication_required")
    root = Path(output_root)
    journals = _load_valid_transactions(root)
    owners = [
        transaction
        for _path, transaction in journals
        if transaction.owns_revision
        and transaction.revision == publication.revision
    ]
    if len(journals) != 1 or len(owners) != 1:
        raise ValueError("publisher_finalized_authority_invalid")
    owner = owners[0]
    revision_root = root / publication.revision
    if (
        owner.phase != "finalized"
        or owner.deck_name != publication.deck_name
        or owner.deck_fingerprint != publication.deck_fingerprint
        or owner.content_root_sha256 != publication.content_root_sha256
        or owner.revision_identity != path_identity(revision_root)
        or owner.staging_identity is not None
        or owner.previous_revision is not None
        or owner.previous_revision_identity is not None
        or owner.previous_owner_transaction_id is not None
    ):
        raise ValueError("publisher_finalized_authority_invalid")


def _reconcile_locked(output_root: Path) -> PublishedOutput | None:
    current: tuple[OutputPublication, Any] | None
    pointer_path = output_root / CURRENT_PATH
    if path_lexists(pointer_path):
        current = resolve_current_publication_unlocked(output_root)
    else:
        current = None
    current_revision = current[0].revision if current is not None else None
    _recover_owned_atomic_temps(
        output_root,
        current_revision=current_revision,
    )
    journals = _load_valid_transactions(output_root)
    _validate_publisher_residue(
        output_root,
        journals=journals,
        current_revision=current_revision,
    )

    journals = [
        (
            journal_path,
            _recover_interrupted_revision_move(
                output_root,
                journal_path,
                transaction,
            ),
        )
        for journal_path, transaction in journals
    ]

    current_owner: tuple[Path, _Transaction] | None = None
    for journal_path, transaction in journals:
        if transaction.revision == current_revision:
            if current_owner is None or transaction.owns_revision:
                current_owner = (journal_path, transaction)

    for journal_path, transaction in journals:
        staging_root = output_root / transaction.staging
        revision_root = output_root / transaction.revision
        if transaction.revision == current_revision:
            if not _cleanup_staging_if_owned(staging_root, transaction):
                raise ValueError(
                    "publisher_owned_staging_cleanup_incomplete"
                )
            if (
                transaction.previous_revision is not None
                and transaction.phase != "finalized"
            ):
                transaction = _continue_or_prepare_old_cleanup(
                    output_root,
                    transaction,
                    journal_path,
                    journals=journals,
                    fault_hook=no_fault,
                )
            if current_owner is not None and journal_path != current_owner[0]:
                _remove_file_if_plain(journal_path)
                continue
            if transaction.phase != "finalized":
                transaction = replace(
                    transaction,
                    staging_identity=None,
                    previous_revision_identity=None,
                    previous_owner_transaction_id=None,
                    phase="finalized",
                )
                _write_transaction(journal_path, transaction)
            continue

        if (
            transaction.owns_revision
            and not path_lexists(revision_root)
            and current_owner is not None
            and current_owner[1].previous_revision == transaction.revision
        ):
            _remove_file_if_plain(journal_path)
            continue

        if current_revision == transaction.previous_revision or current is None:
            staging_cleanup_complete = _cleanup_staging_if_owned(
                staging_root,
                transaction,
            )
            revision_cleanup_complete = True
            if transaction.owns_revision:
                revision_cleanup_complete = _remove_owned_tree_if_present(
                    revision_root,
                    expected_identity=transaction.revision_identity,
                    require_verified_root=transaction.content_root_sha256,
                )
            if not revision_cleanup_complete:
                raise ValueError(
                    "publisher_owned_revision_cleanup_incomplete"
                )
            if not staging_cleanup_complete:
                raise ValueError(
                    "publisher_owned_staging_cleanup_incomplete"
                )
            _remove_file_if_plain(journal_path)

    if current is None:
        return None
    publication = current[0]
    _cleanup_detached_owned_revisions(output_root, publication)
    revision_root = output_root / publication.revision
    return PublishedOutput(
        output_root=output_root,
        revision_root=revision_root,
        package_root=revision_root / "04_package",
        content_root_sha256=publication.content_root_sha256,
        reused_existing_revision=True,
    )


def _cleanup_detached_owned_revisions(
    output_root: Path,
    publication: OutputPublication,
) -> None:
    """Converge verified owned history through the crash-safe cleanup journal."""

    current_revision = publication.revision
    current_root = output_root / current_revision
    while True:
        journals = _load_valid_transactions(output_root)
        current_owners = [
            (path, transaction)
            for path, transaction in journals
            if transaction.revision == current_revision
            and transaction.owns_revision
        ]
        if len(current_owners) != 1:
            raise ValueError("publisher_current_owner_invalid")
        _current_owner_path, current_owner = current_owners[0]
        current_identity = path_identity(current_root)
        verified_current = snapshot_and_verify_revision(current_root)
        if (
            current_owner.phase != "finalized"
            or current_owner.revision_identity != current_identity
            or current_owner.deck_name != publication.deck_name
            or current_owner.deck_fingerprint
            != publication.deck_fingerprint
            or current_owner.content_root_sha256
            != publication.content_root_sha256
            or verified_current.manifest.deck_name
            != publication.deck_name
            or verified_current.manifest.deck_fingerprint
            != publication.deck_fingerprint
            or verified_current.manifest.content_root_sha256
            != publication.content_root_sha256
        ):
            raise ValueError("publisher_current_owner_invalid")

        revision_names: list[str] = []
        with os.scandir(output_root / "revisions") as iterator:
            for entry in iterator:
                if len(revision_names) >= _MAX_TRANSACTION_FILES * 2 + 1:
                    raise ValueError("publisher_residue_count_limit")
                status = Path(entry.path).lstat()
                if (
                    status_is_reparse(status)
                    or not stat.S_ISDIR(status.st_mode)
                ):
                    raise ValueError("publisher_revision_residue_invalid")
                revision_names.append(entry.name)
        stale_names = sorted(
            name
            for name in revision_names
            if name != Path(current_revision).name
        )
        if not stale_names:
            if len(journals) != 1 or journals[0][1] != current_owner:
                raise ValueError("publisher_noncurrent_journal_residue")
            _require_exact_directory_entries(
                output_root / "revisions",
                allowed={Path(current_revision).name},
                maximum=2,
                directories_only=True,
            )
            return

        stale_revision = f"revisions/{stale_names[0]}"
        owners = [
            (path, transaction)
            for path, transaction in journals
            if transaction.revision == stale_revision
            and transaction.owns_revision
        ]
        if len(owners) != 1:
            raise ValueError("publisher_cleanup_owner_ambiguous")
        _owner_path, owner = owners[0]
        if owner.phase != "finalized":
            raise ValueError("publisher_cleanup_owner_not_finalized")
        active_references = [
            transaction
            for _path, transaction in journals
            if transaction.transaction_id != owner.transaction_id
            and transaction.phase != "finalized"
            and (
                transaction.revision == stale_revision
                or transaction.previous_revision == stale_revision
            )
        ]
        if active_references:
            raise ValueError("publisher_cleanup_reference_ambiguous")
        stale_root = output_root / stale_revision
        stale_identity = path_identity(stale_root)
        verified_stale = snapshot_and_verify_revision(stale_root)
        if (
            owner.revision_identity != stale_identity
            or owner.revision
            != f"revisions/sha256-{owner.content_root_sha256}"
            or verified_stale.manifest.content_root_sha256
            != owner.content_root_sha256
            or verified_stale.manifest.deck_name != owner.deck_name
            or verified_stale.manifest.deck_fingerprint
            != owner.deck_fingerprint
        ):
            raise ValueError("publisher_cleanup_manifest_mismatch")

        coordinator_id = uuid.uuid4().hex
        coordinator = _Transaction(
            schema_version=_TRANSACTION_SCHEMA_VERSION,
            transaction_id=coordinator_id,
            deck_name=publication.deck_name,
            deck_fingerprint=publication.deck_fingerprint,
            content_root_sha256=publication.content_root_sha256,
            staging=f"revisions/.staging-{coordinator_id}",
            revision=current_revision,
            previous_revision=stale_revision,
            previous_revision_identity=None,
            previous_owner_transaction_id=None,
            staging_identity=None,
            revision_identity=current_identity,
            owns_revision=False,
            phase="pointer_committed",
        )
        coordinator_path = _journal_path(output_root, coordinator_id)
        _write_transaction(coordinator_path, coordinator)
        _cleanup_after_commit(
            output_root,
            coordinator,
            coordinator_path,
            fault_hook=no_fault,
        )


def _validate_publisher_residue(
    output_root: Path,
    *,
    journals: list[tuple[Path, _Transaction]],
    current_revision: str | None,
) -> None:
    if current_revision is not None:
        current_owners = [
            transaction
            for _path, transaction in journals
            if transaction.revision == current_revision
            and transaction.owns_revision
            and transaction.revision_identity is not None
        ]
        if len(current_owners) != 1:
            raise ValueError("publisher_current_owner_invalid")
    allowed_root = {
        ".publish.lock",
        ".publisher",
        "revisions",
        *(("current.json",) if current_revision is not None else ()),
    }
    _require_exact_directory_entries(
        output_root,
        allowed=allowed_root,
        maximum=10,
    )
    _require_exact_directory_entries(
        output_root / ".publisher",
        allowed={"transactions"},
        maximum=4,
    )
    allowed_revisions: set[str] = set()
    if current_revision is not None:
        allowed_revisions.add(Path(current_revision).name)
    for _journal_path, transaction in journals:
        if path_lexists(output_root / transaction.staging):
            allowed_revisions.add(Path(transaction.staging).name)
        if path_lexists(output_root / transaction.revision):
            allowed_revisions.add(Path(transaction.revision).name)
    _require_exact_directory_entries(
        output_root / "revisions",
        allowed=allowed_revisions,
        maximum=_MAX_TRANSACTION_FILES * 2 + 1,
        directories_only=True,
    )


def _require_exact_directory_entries(
    directory: Path,
    *,
    allowed: set[str],
    maximum: int,
    directories_only: bool = False,
) -> None:
    require_plain_directory(directory)
    names: list[str] = []
    folded: set[str] = set()
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(names) >= maximum:
                raise ValueError("publisher_residue_count_limit")
            child = Path(entry.path)
            status = child.lstat()
            if status_is_reparse(status):
                raise ValueError("publisher_residue_reparse")
            if directories_only and not stat.S_ISDIR(status.st_mode):
                raise ValueError("publisher_revision_residue_invalid")
            folded_name = entry.name.casefold()
            if folded_name in folded:
                raise ValueError("publisher_residue_casefold_collision")
            folded.add(folded_name)
            names.append(entry.name)
    if set(names) != allowed:
        raise ValueError("publisher_residue_invalid")


def _recover_interrupted_revision_move(
    output_root: Path,
    journal_path: Path,
    transaction: _Transaction,
) -> _Transaction:
    """Close the rename-to-journal window using the recorded inode identity."""

    if (
        transaction.phase not in {"staging_owned", "staging_verified"}
        or transaction.staging_identity is None
    ):
        return transaction
    staging_root = output_root / transaction.staging
    revision_root = output_root / transaction.revision
    try:
        staging_identity = path_identity(staging_root)
    except FileNotFoundError:
        staging_identity = None
    try:
        revision_identity = path_identity(revision_root)
    except FileNotFoundError:
        revision_identity = None
    if staging_identity is not None:
        return transaction
    if revision_identity != transaction.staging_identity:
        return transaction
    try:
        verified = snapshot_and_verify_revision(revision_root)
    except Exception:
        return transaction
    if (
        verified.manifest.content_root_sha256
        != transaction.content_root_sha256
        or verified.manifest.deck_name != transaction.deck_name
        or verified.manifest.deck_fingerprint
        != transaction.deck_fingerprint
    ):
        return transaction
    recovered = replace(
        transaction,
        staging_identity=None,
        revision_identity=revision_identity,
        owns_revision=True,
        phase="revision_ready",
    )
    _write_transaction(journal_path, recovered)
    return recovered


def _cleanup_after_commit(
    output_root: Path,
    transaction: _Transaction,
    journal_path: Path,
    *,
    fault_hook: FaultHook,
) -> None:
    if transaction.previous_revision is not None:
        journals = _load_valid_transactions(output_root)
        transaction = _continue_or_prepare_old_cleanup(
            output_root,
            transaction,
            journal_path,
            journals=journals,
            fault_hook=fault_hook,
        )
    current_owner = transaction
    if not transaction.owns_revision:
        for other_path, other in _load_valid_transactions(output_root):
            if (
                other_path != journal_path
                and other.revision == transaction.revision
                and other.owns_revision
            ):
                current_owner = other
                _remove_file_if_plain(journal_path)
                break
    if current_owner is transaction:
        _write_transaction(
            journal_path,
            replace(
                transaction,
                staging_identity=None,
                previous_revision_identity=None,
                previous_owner_transaction_id=None,
                phase="finalized",
            ),
            fault_hook=fault_hook,
        )


def _continue_or_prepare_old_cleanup(
    output_root: Path,
    transaction: _Transaction,
    journal_path: Path,
    *,
    journals: list[tuple[Path, _Transaction]],
    fault_hook: FaultHook,
) -> _Transaction:
    previous_revision = transaction.previous_revision
    if (
        previous_revision is None
        or previous_revision == transaction.revision
    ):
        return transaction
    previous_root = output_root / previous_revision
    try:
        actual_identity = path_identity(previous_root)
    except FileNotFoundError:
        actual_identity = None
    if transaction.phase == "cleanup_started":
        if actual_identity is None:
            owner_path = next(
                (
                    path
                    for path, candidate in journals
                    if candidate.transaction_id
                    == transaction.previous_owner_transaction_id
                    and candidate.revision == previous_revision
                    and candidate.owns_revision
                    and candidate.revision_identity
                    == transaction.previous_revision_identity
                ),
                None,
            )
            if owner_path is not None:
                _remove_file_if_plain(owner_path)
            return transaction
        owner = next(
            (
                (path, candidate)
                for path, candidate in journals
                if candidate.transaction_id
                == transaction.previous_owner_transaction_id
                and candidate.revision == previous_revision
                and candidate.owns_revision
                and candidate.revision_identity
                == transaction.previous_revision_identity
            ),
            None,
        )
        if owner is None:
            raise ValueError("publisher_cleanup_owner_missing")
        owner_path, _owner_transaction = owner
        if actual_identity != transaction.previous_revision_identity:
            raise ValueError("publisher_cleanup_identity_changed")
    else:
        matching = [
            (path, candidate)
            for path, candidate in journals
            if candidate.revision == previous_revision
            and candidate.owns_revision
            and candidate.revision_identity == actual_identity
        ]
        if len(matching) != 1:
            raise ValueError("publisher_cleanup_owner_ambiguous")
        owner_path, owner_transaction = matching[0]
        verified = snapshot_and_verify_revision(previous_root)
        if (
            verified.manifest.content_root_sha256
            != owner_transaction.content_root_sha256
            or verified.manifest.deck_name != owner_transaction.deck_name
            or verified.manifest.deck_fingerprint
            != owner_transaction.deck_fingerprint
        ):
            raise ValueError("publisher_cleanup_manifest_mismatch")
        transaction = replace(
            transaction,
            previous_revision_identity=actual_identity,
            previous_owner_transaction_id=owner_transaction.transaction_id,
            phase="cleanup_started",
        )
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )
    _remove_owned_tree(
        previous_root,
        expected_identity=transaction.previous_revision_identity,
        after_first_delete=lambda: fault_hook(
            "during_old_revision_cleanup"
        ),
    )
    _remove_file_if_plain(owner_path)
    return transaction


def _cleanup_staging_if_owned(
    staging_root: Path,
    transaction: _Transaction,
) -> bool:
    if transaction.staging_identity is None:
        if not path_lexists(staging_root):
            return True
        if transaction.phase != "prepared":
            return False
        try:
            require_plain_directory(staging_root)
            if any(staging_root.iterdir()):
                return False
            secure_rmdir(
                staging_root,
                expected_identity=path_identity(staging_root),
                expected_parent_identity=path_identity(
                    staging_root.parent
                ),
            )
        except (OSError, ValueError):
            return False
        return True
    return _remove_owned_tree_if_present(
        staging_root,
        expected_identity=transaction.staging_identity,
    )


def _remove_owned_tree_if_present(
    path: Path,
    *,
    expected_identity: tuple[int, int, int] | None,
    require_verified_root: str | None = None,
) -> bool:
    if expected_identity is None:
        return False
    try:
        current_identity = path_identity(path)
    except FileNotFoundError:
        return True
    if current_identity != expected_identity:
        return False
    if require_verified_root is not None:
        try:
            verified = snapshot_and_verify_revision(path)
        except Exception:
            return False
        if verified.manifest.content_root_sha256 != require_verified_root:
            return False
    _remove_owned_tree(path, expected_identity=expected_identity)
    return True


def _remove_owned_tree(
    path: Path,
    *,
    expected_identity: tuple[int, int, int],
    after_first_delete: Callable[[], None] | None = None,
) -> None:
    if path_identity(path) != expected_identity:
        raise ValueError("publisher_owned_path_identity_changed")
    rows: list[tuple[Path, os.stat_result]] = []
    pending = [(path, "", 0)]
    directory_count = 0
    node_count = 0
    while pending:
        directory_path, prefix, depth = pending.pop()
        if depth > MAX_FILESYSTEM_DEPTH:
            raise ValueError("publisher_owned_path_depth_limit")
        directory_status = directory_path.lstat()
        if (
            not stat.S_ISDIR(directory_status.st_mode)
            or status_is_reparse(directory_status)
        ):
            raise ValueError("publisher_owned_path_reparse")
        count = 0
        with os.scandir(directory_path) as iterator:
            for entry in iterator:
                count += 1
                if count > MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY:
                    raise ValueError(
                        "publisher_owned_path_directory_entry_limit"
                    )
                node_count += 1
                if node_count > MAX_FILESYSTEM_NODES:
                    raise ValueError("publisher_owned_path_node_limit")
                child = Path(entry.path)
                status = child.lstat()
                if status_is_reparse(status) or entry.is_symlink():
                    raise ValueError("publisher_owned_path_reparse")
                relative = f"{prefix}{entry.name}"
                if len(relative.encode("utf-8")) > MAX_RUN_PATH_BYTES:
                    raise ValueError(
                        "publisher_owned_path_length_limit"
                    )
                if canonical_relative_path(relative) != relative:
                    raise ValueError("publisher_owned_path_invalid")
                rows.append((child, status))
                if stat.S_ISDIR(status.st_mode):
                    directory_count += 1
                    if directory_count > MAX_FILESYSTEM_DIRECTORIES:
                        raise ValueError(
                            "publisher_owned_path_directory_limit"
                        )
                    pending.append(
                        (child, f"{relative}/", depth + 1)
                    )
                elif not stat.S_ISREG(status.st_mode):
                    raise ValueError(
                        "publisher_owned_path_entry_invalid"
                    )
    deleted_one = False
    for child, expected_status in sorted(
        rows,
        key=lambda row: len(row[0].parts),
        reverse=True,
    ):
        try:
            current = child.lstat()
        except FileNotFoundError:
            continue
        if _identity(current) != _identity(expected_status):
            raise ValueError("publisher_owned_path_identity_changed")
        if stat.S_ISDIR(current.st_mode):
            secure_rmdir(
                child,
                expected_identity=_identity(expected_status),
                expected_parent_identity=path_identity(child.parent),
            )
        elif stat.S_ISREG(current.st_mode):
            secure_unlink(
                child,
                expected_identity=_identity(expected_status),
                expected_parent_identity=path_identity(child.parent),
            )
        else:
            raise ValueError("publisher_owned_path_entry_invalid")
        if not deleted_one:
            deleted_one = True
            if after_first_delete is not None:
                after_first_delete()
    if path_identity(path) != expected_identity:
        raise ValueError("publisher_owned_path_identity_changed")
    secure_rmdir(
        path,
        expected_identity=expected_identity,
        expected_parent_identity=path_identity(path.parent),
    )


def _new_transaction(
    rendered: RenderedConfigureRun,
    current: PublishedOutput | None,
) -> _Transaction:
    transaction_id = uuid.uuid4().hex
    return _Transaction(
        schema_version=_TRANSACTION_SCHEMA_VERSION,
        transaction_id=transaction_id,
        deck_name=rendered.model.deck_name,
        deck_fingerprint=rendered.model.deck_fingerprint,
        content_root_sha256=rendered.content_root_sha256,
        staging=f"revisions/.staging-{transaction_id}",
        revision=f"revisions/sha256-{rendered.content_root_sha256}",
        previous_revision=(
            current.revision_root.relative_to(
                current.output_root
            ).as_posix()
            if current is not None
            else None
        ),
        previous_revision_identity=None,
        previous_owner_transaction_id=None,
        staging_identity=None,
        revision_identity=None,
        owns_revision=False,
        phase="prepared",
    )


def _write_rendered_run(
    rendered: RenderedConfigureRun,
    destination: Path,
) -> None:
    """Write immutable bytes without following or overwriting any path."""

    guard = capture_plain_ancestor_guard(destination)
    require_plain_directory(destination)
    root_identity = path_identity(destination)
    owned_directories: dict[Path, tuple[int, int, int]] = {
        destination: root_identity
    }
    content = tuple(
        artifact
        for artifact in rendered.artifacts
        if artifact.relative_path != "package_manifest.json"
    )
    manifests = tuple(
        artifact
        for artifact in rendered.artifacts
        if artifact.relative_path == "package_manifest.json"
    )
    if len(manifests) != 1:
        raise ValueError("rendered_configure_run_manifest_missing")
    for artifact in (*content, *manifests):
        guard.validate()
        if path_identity(destination) != root_identity:
            raise ValueError("publication_staging_identity_changed")
        target = destination / artifact.relative_path
        current = destination
        for part in Path(artifact.relative_path).parts[:-1]:
            current /= part
            if current not in owned_directories:
                if path_lexists(current):
                    raise ValueError("publication_staging_path_preexisting")
                created_identity = secure_create_directory(
                    current,
                    expected_parent_identity=owned_directories[
                        current.parent
                    ],
                )
                require_plain_directory(current)
                if path_identity(current) != created_identity:
                    raise ValueError(
                        "publication_staging_directory_changed"
                    )
                owned_directories[current] = created_identity
            elif path_identity(current) != owned_directories[current]:
                raise ValueError("publication_staging_directory_changed")
        if path_lexists(target):
            raise ValueError("publication_staging_path_preexisting")
        descriptor = secure_open_file_descriptor(
            target,
            create=True,
            write=True,
            expected_parent_identity=owned_directories[target.parent],
        )
        try:
            opened = os.fstat(descriptor)
            target_status = target.lstat()
            if (
                path_identity_from_status(opened)
                != path_identity_from_status(target_status)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or status_is_reparse(target_status)
            ):
                raise ValueError("publication_staging_file_identity_invalid")
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(artifact.content)
                handle.flush()
                os.fsync(descriptor)
            if (
                path_identity(target)
                != path_identity_from_status(opened)
                or any(
                    path_identity(path) != identity
                    for path, identity in owned_directories.items()
                )
            ):
                raise ValueError("publication_staging_path_changed")
        finally:
            os.close(descriptor)
        status = plain_file_status(target)
        if read_file_no_follow(
            target,
            expected_status=status,
            maximum_size=len(artifact.content),
        ) != artifact.content:
            raise ValueError("publication_staging_write_failed")
    guard.validate()
    if path_identity(destination) != root_identity:
        raise ValueError("publication_staging_identity_changed")


def _replace_pointer_if_unchanged(
    output_root: Path,
    before: _PointerSnapshot,
    content: bytes,
    *,
    transaction_id: str,
    fault_hook: FaultHook,
) -> None:
    """Commit the pointer for cooperative publishers holding ``.publish.lock``.

    The comparison protects against stale cooperative state and injected crash
    faults. A non-cooperating same-user process mutating ``current.json`` in the
    final kernel commit window is outside the publication contract.
    """
    pointer_path = output_root / CURRENT_PATH

    def compare_and_swap() -> None:
        if _snapshot_pointer(output_root) != before:
            raise ValueError("current_output_concurrent_change")

    _owned_atomic_replace(
        pointer_path,
        content,
        temp_path=(
            output_root
            / ".publisher"
            / "transactions"
            / f".{transaction_id}.current.tmp"
        ),
        before_replace=compare_and_swap,
        fault_hook=fault_hook,
        temp_stage="after_pointer_temp_write",
    )


def _owned_atomic_replace(
    target: Path,
    content: bytes,
    *,
    temp_path: Path,
    before_replace: Callable[[], None] | None = None,
    fault_hook: FaultHook = no_fault,
    temp_stage: str,
) -> None:
    if path_lexists(temp_path):
        raise ValueError("publisher_owned_temp_preexisting")
    parent_guard = capture_plain_ancestor_guard(target.parent)
    require_plain_directory(target.parent)
    require_plain_directory(temp_path.parent)
    target_parent_identity = path_identity(target.parent)
    temp_parent_identity = path_identity(temp_path.parent)
    descriptor = secure_open_file_descriptor(
        temp_path,
        create=True,
        write=True,
        expected_parent_identity=temp_parent_identity,
    )
    try:
        opened = os.fstat(descriptor)
        temp_status = temp_path.lstat()
        if (
            path_identity_from_status(opened)
            != path_identity_from_status(temp_status)
            or status_is_reparse(temp_status)
            or opened.st_nlink != 1
        ):
            raise ValueError("publisher_owned_temp_identity_invalid")
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent_guard.validate()
    status = plain_file_status(temp_path)
    if read_file_no_follow(
        temp_path,
        expected_status=status,
        maximum_size=len(content),
    ) != content:
        raise ValueError("publisher_owned_temp_verification_failed")
    fault_hook(temp_stage)
    if before_replace is not None:
        before_replace()
    parent_guard.validate()
    secure_replace(
        temp_path,
        target,
        expected_source_identity=path_identity_from_status(status),
        expected_source_parent_identity=temp_parent_identity,
        expected_target_parent_identity=target_parent_identity,
    )
    parent_guard.validate()


def _snapshot_pointer(output_root: Path) -> _PointerSnapshot:
    pointer_path = output_root / CURRENT_PATH
    try:
        status = plain_file_status(pointer_path)
    except FileNotFoundError:
        return _PointerSnapshot(False, None, None)
    content = read_file_no_follow(
        pointer_path,
        expected_status=status,
        maximum_size=1024 * 1024,
    )
    return _PointerSnapshot(True, content, _file_state(status))


def _ensure_layout(output_root: Path) -> None:
    _secure_create_directory_chain(output_root)
    for child in (
        output_root / "revisions",
        output_root / ".publisher",
        output_root / ".publisher" / "transactions",
    ):
        if not path_lexists(child):
            try:
                secure_create_directory(
                    child,
                    expected_parent_identity=path_identity(child.parent),
                )
            except FileExistsError:
                pass
        require_plain_directory(child)
    lock_path = output_root / ".publish.lock"
    if path_lexists(lock_path):
        plain_file_status(lock_path)


def _secure_create_directory_chain(path: Path) -> None:
    missing: list[Path] = []
    current = Path(path).absolute()
    while not path_lexists(current):
        missing.append(current)
        current = current.parent
    require_plain_directory(current)
    guard = capture_plain_ancestor_guard(current)
    for directory in reversed(missing):
        guard.validate()
        try:
            secure_create_directory(
                directory,
                expected_parent_identity=path_identity(directory.parent),
            )
        except FileExistsError:
            require_plain_directory(directory)
        require_plain_directory(directory)
        guard = capture_plain_ancestor_guard(directory)


def _validate_existing_layout(output_root: Path) -> None:
    require_plain_directory(output_root)
    for path in (
        output_root / "revisions",
        output_root / ".publisher",
        output_root / ".publisher" / "transactions",
    ):
        require_plain_directory(path)
    plain_file_status(output_root / ".publish.lock")


def _capture_layout_guards(
    output_root: Path,
) -> tuple[FilesystemPathGuard, ...]:
    return (
        capture_plain_ancestor_guard(output_root / ".publish.lock"),
        capture_plain_ancestor_guard(output_root / "revisions"),
        capture_plain_ancestor_guard(
            output_root / ".publisher" / "transactions"
        ),
    )


def _validate_layout_guards(
    guards: tuple[FilesystemPathGuard, ...],
) -> None:
    for guard in guards:
        guard.validate()


def _journal_path(output_root: Path, transaction_id: str) -> Path:
    return (
        output_root
        / ".publisher"
        / "transactions"
        / f"{transaction_id}.json"
    )


def _recover_owned_atomic_temps(
    output_root: Path,
    *,
    current_revision: str | None,
) -> None:
    directory = output_root / ".publisher" / "transactions"
    require_plain_directory(directory)
    entries: list[tuple[Path, os.stat_result]] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(entries) >= _MAX_TRANSACTION_FILES * 3:
                raise ValueError("publisher_transaction_count_limit")
            path = Path(entry.path)
            status = path.lstat()
            if (
                not stat.S_ISREG(status.st_mode)
                or status_is_reparse(status)
                or status.st_nlink != 1
                or status.st_size > _MAX_TRANSACTION_FILE_BYTES
            ):
                raise ValueError("publisher_transaction_file_invalid")
            entries.append((path, status))
    finals: dict[str, tuple[Path, _Transaction, tuple[int, int, int]]] = {}
    journal_temps: dict[
        str, tuple[Path, _Transaction, tuple[int, int, int]]
    ] = {}
    pointer_temps: list[
        tuple[
            str,
            Path,
            OutputPublication,
            tuple[int, int, int],
        ]
    ] = []
    for path, status in entries:
        content = read_file_no_follow(
            path,
            expected_status=status,
            maximum_size=_MAX_TRANSACTION_FILE_BYTES,
        )
        final_match = re.fullmatch(r"([0-9a-f]{32})\.json", path.name)
        journal_match = re.fullmatch(
            r"\.([0-9a-f]{32})\.journal\.tmp",
            path.name,
        )
        pointer_match = re.fullmatch(
            r"\.([0-9a-f]{32})\.current\.tmp",
            path.name,
        )
        identity = path_identity_from_status(status)
        if final_match is not None:
            transaction = _parse_transaction(content)
            transaction_id = final_match.group(1)
            if transaction.transaction_id != transaction_id:
                raise ValueError("publisher_transaction_name_mismatch")
            finals[transaction_id] = (path, transaction, identity)
        elif journal_match is not None:
            transaction = _parse_transaction(content)
            transaction_id = journal_match.group(1)
            if transaction.transaction_id != transaction_id:
                raise ValueError("publisher_transaction_temp_mismatch")
            journal_temps[transaction_id] = (
                path,
                transaction,
                identity,
            )
        elif pointer_match is not None:
            pointer_temps.append(
                (
                    pointer_match.group(1),
                    path,
                    parse_output_publication(content),
                    identity,
                )
            )
        else:
            raise ValueError("publisher_transaction_residue_invalid")
    effective = dict(finals)
    journal_actions: list[
        tuple[str, Path, Path, tuple[int, int, int]]
    ] = []
    for transaction_id, temp_row in journal_temps.items():
        temp_path, temp_transaction, temp_identity = temp_row
        final_row = finals.get(transaction_id)
        final_path = _journal_path(output_root, transaction_id)
        if final_row is None:
            effective[transaction_id] = (
                final_path,
                temp_transaction,
                temp_identity,
            )
            journal_actions.append(
                ("promote_create", temp_path, final_path, temp_identity)
            )
            continue
        _final_path, final_transaction, _final_identity = final_row
        if not _same_transaction_identity(
            final_transaction,
            temp_transaction,
        ):
            raise ValueError("publisher_transaction_temp_conflict")
        temp_rank = _phase_rank(temp_transaction.phase)
        final_rank = _phase_rank(final_transaction.phase)
        if temp_rank < final_rank:
            journal_actions.append(
                ("remove", temp_path, final_path, temp_identity)
            )
        elif temp_rank == final_rank:
            if temp_transaction != final_transaction:
                raise ValueError("publisher_transaction_temp_conflict")
            journal_actions.append(
                ("remove", temp_path, final_path, temp_identity)
            )
        else:
            allowed_skip = (
                final_transaction.phase == "pointer_committed"
                and temp_transaction.phase == "finalized"
                and (
                    final_transaction.previous_revision is None
                    or final_transaction.previous_revision
                    == final_transaction.revision
                )
            )
            if temp_rank != final_rank + 1 and not allowed_skip:
                raise ValueError("publisher_transaction_phase_jump")
            effective[transaction_id] = (
                final_path,
                temp_transaction,
                temp_identity,
            )
            journal_actions.append(
                ("promote_replace", temp_path, final_path, temp_identity)
            )
    pointer_actions: list[tuple[Path, tuple[int, int, int]]] = []
    for transaction_id, path, publication, identity in pointer_temps:
        row = effective.get(transaction_id)
        if row is None:
            raise ValueError("publisher_pointer_temp_owner_missing")
        transaction = row[1]
        if (
            publication.deck_name != transaction.deck_name
            or publication.deck_fingerprint
            != transaction.deck_fingerprint
            or publication.revision != transaction.revision
            or publication.content_root_sha256
            != transaction.content_root_sha256
        ):
            raise ValueError("publisher_pointer_temp_owner_mismatch")
        pointer_actions.append((path, identity))
    _validate_publisher_residue(
        output_root,
        journals=[
            (row[0], row[1])
            for row in effective.values()
        ],
        current_revision=current_revision,
    )
    guard = capture_plain_ancestor_guard(directory)
    directory_identity = path_identity(directory)
    for action, temp_path, final_path, identity in journal_actions:
        guard.validate()
        if path_identity(temp_path) != identity:
            raise ValueError("publisher_owned_temp_identity_changed")
        if action in {"promote_create", "promote_replace"}:
            secure_replace(
                temp_path,
                final_path,
                expected_source_identity=identity,
                expected_source_parent_identity=directory_identity,
                expected_target_parent_identity=directory_identity,
                expected_target_absent=action == "promote_create",
            )
        else:
            secure_unlink(
                temp_path,
                expected_identity=identity,
                expected_parent_identity=directory_identity,
            )
        guard.validate()
    for path, identity in pointer_actions:
        guard.validate()
        if path_identity(path) != identity:
            raise ValueError("publisher_owned_temp_identity_changed")
        secure_unlink(
            path,
            expected_identity=identity,
            expected_parent_identity=directory_identity,
        )
        guard.validate()


def _same_transaction_identity(
    left: _Transaction,
    right: _Transaction,
) -> bool:
    return (
        left.transaction_id,
        left.deck_name,
        left.deck_fingerprint,
        left.content_root_sha256,
        left.staging,
        left.revision,
        left.previous_revision,
    ) == (
        right.transaction_id,
        right.deck_name,
        right.deck_fingerprint,
        right.content_root_sha256,
        right.staging,
        right.revision,
        right.previous_revision,
    )


def _phase_rank(phase: str) -> int:
    order = (
        "prepared",
        "staging_owned",
        "staging_verified",
        "revision_ready",
        "pointer_committed",
        "cleanup_started",
        "finalized",
    )
    return order.index(phase)


def _load_valid_transactions(
    output_root: Path,
) -> list[tuple[Path, _Transaction]]:
    directory = output_root / ".publisher" / "transactions"
    require_plain_directory(directory)
    result: list[tuple[Path, _Transaction]] = []
    entries: list[os.DirEntry[str]] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(entries) >= _MAX_TRANSACTION_FILES:
                raise ValueError("publisher_transaction_count_limit")
            entries.append(entry)
    total_bytes = 0
    for entry in sorted(entries, key=lambda row: row.name):
        if not re.fullmatch(r"[0-9a-f]{32}\.json", entry.name):
            raise ValueError("publisher_transaction_residue_invalid")
        status = Path(entry.path).lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or status_is_reparse(status)
            or status.st_nlink != 1
            or status.st_size > _MAX_TRANSACTION_FILE_BYTES
        ):
            raise ValueError("publisher_transaction_file_invalid")
        total_bytes += status.st_size
        if total_bytes > _MAX_TRANSACTION_BYTES:
            raise ValueError("publisher_transaction_bytes_limit")
        path = Path(entry.path)
        try:
            transaction = _parse_transaction(
                read_file_no_follow(
                    path,
                    expected_status=status,
                    maximum_size=_MAX_TRANSACTION_FILE_BYTES,
                )
            )
        except Exception as error:
            raise ValueError("publisher_transaction_invalid") from error
        if transaction.transaction_id != entry.name[:-5]:
            raise ValueError("publisher_transaction_name_mismatch")
        result.append((path, transaction))
    owners: dict[str, list[_Transaction]] = {}
    for _path, transaction in result:
        if transaction.owns_revision:
            owners.setdefault(transaction.revision, []).append(transaction)
    if any(len(rows) != 1 for rows in owners.values()):
        raise ValueError("publisher_revision_owner_ambiguous")
    return result


def _write_transaction(
    path: Path,
    transaction: _Transaction,
    *,
    fault_hook: FaultHook = no_fault,
) -> None:
    def transaction_fault(stage: str) -> None:
        fault_hook(stage)
        if stage == "after_journal_temp_write":
            fault_hook(
                f"after_journal_{transaction.phase}_temp_write"
            )

    _owned_atomic_replace(
        path,
        _transaction_bytes(transaction),
        temp_path=path.with_name(
            f".{transaction.transaction_id}.journal.tmp"
        ),
        fault_hook=transaction_fault,
        temp_stage="after_journal_temp_write",
    )


def _transaction_bytes(transaction: _Transaction) -> bytes:
    payload = {
        "schema_version": transaction.schema_version,
        "transaction_id": transaction.transaction_id,
        "deck_name": transaction.deck_name,
        "deck_fingerprint": transaction.deck_fingerprint,
        "content_root_sha256": transaction.content_root_sha256,
        "staging": transaction.staging,
        "revision": transaction.revision,
        "previous_revision": transaction.previous_revision,
        "previous_revision_identity": (
            list(transaction.previous_revision_identity)
            if transaction.previous_revision_identity is not None
            else None
        ),
        "previous_owner_transaction_id": (
            transaction.previous_owner_transaction_id
        ),
        "staging_identity": (
            list(transaction.staging_identity)
            if transaction.staging_identity is not None
            else None
        ),
        "revision_identity": (
            list(transaction.revision_identity)
            if transaction.revision_identity is not None
            else None
        ),
        "owns_revision": transaction.owns_revision,
        "phase": transaction.phase,
    }
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _parse_transaction(content: bytes) -> _Transaction:
    payload = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=_unique_json_object,
    )
    if not isinstance(payload, dict) or set(payload) != _JOURNAL_KEYS:
        raise ValueError("publisher_transaction_invalid")
    transaction = _Transaction(
        schema_version=payload["schema_version"],
        transaction_id=payload["transaction_id"],
        deck_name=payload["deck_name"],
        deck_fingerprint=payload["deck_fingerprint"],
        content_root_sha256=payload["content_root_sha256"],
        staging=payload["staging"],
        revision=payload["revision"],
        previous_revision=payload["previous_revision"],
        previous_revision_identity=_parse_identity(
            payload["previous_revision_identity"]
        ),
        previous_owner_transaction_id=payload[
            "previous_owner_transaction_id"
        ],
        staging_identity=_parse_identity(payload["staging_identity"]),
        revision_identity=_parse_identity(payload["revision_identity"]),
        owns_revision=payload["owns_revision"],
        phase=payload["phase"],
    )
    if content != _transaction_bytes(transaction):
        raise ValueError("publisher_transaction_noncanonical")
    return transaction


def _parse_identity(value: object) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(item) is not int or item < 0 for item in value)
    ):
        raise ValueError("publisher_transaction_identity_invalid")
    return value[0], value[1], value[2]


def _remove_file_if_plain(path: Path) -> None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(status.st_mode) or status_is_reparse(status):
        return
    secure_unlink(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=path_identity(path.parent),
    )


def _canonical_revision(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split("/")
    return (
        len(parts) == 2
        and parts[0] == "revisions"
        and bool(_REVISION_NAME.fullmatch(parts[1]))
    )


def _identity_or_none(
    value: tuple[int, int, int] | None,
) -> bool:
    return value is None or (
        isinstance(value, tuple)
        and len(value) == 3
        and all(type(item) is int and item >= 0 for item in value)
    )


def _valid_phase_state(transaction: _Transaction) -> bool:
    cleanup_bound = (
        transaction.previous_revision_identity is not None
        and transaction.previous_owner_transaction_id is not None
        and transaction.previous_revision is not None
    )
    if transaction.phase == "cleanup_started":
        return (
            cleanup_bound
            and transaction.staging_identity is None
            and transaction.revision_identity is not None
        )
    if (
        transaction.previous_revision_identity is not None
        or transaction.previous_owner_transaction_id is not None
    ):
        return False
    if transaction.phase == "prepared":
        return (
            transaction.staging_identity is None
            and transaction.revision_identity is None
            and not transaction.owns_revision
        )
    if transaction.phase in {"staging_owned", "staging_verified"}:
        return (
            transaction.staging_identity is not None
            and transaction.revision_identity is None
            and not transaction.owns_revision
        )
    return (
        transaction.staging_identity is None
        and transaction.revision_identity is not None
    )


def _identity(status: os.stat_result) -> tuple[int, int, int]:
    return status.st_dev, status.st_ino, status.st_mode


def _file_state(
    status: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _unique_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = (
    "PublishedOutput",
    "publish_configure_run",
    "reconcile_output",
)
