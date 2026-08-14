"""Validate and explicitly install the embedded HSConfig Codex skill bundle."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
from importlib import resources
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata
from urllib.parse import urlsplit
import uuid

import yaml
from yaml.constructor import ConstructorError

from hsconfig.atomic_io import ExclusiveFileLock, atomic_write_bytes
from hsconfig.package_io import (
    path_identity,
    path_identity_from_status,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_no_alternate_data_streams,
    require_plain_directory,
    secure_create_directory,
    secure_open_file_descriptor,
    secure_replace,
    secure_rmdir_verified,
    secure_unlink,
    secure_unlink_verified,
    snapshot_bounded_filesystem_package,
)
from hsconfig.publishable_tree import PublishableTreeError, _scan_markdown_document
from hsconfig.run_manifest import MAX_RUN_TOTAL_BYTES


BUNDLE_RESOURCE_NAME = "codex_skill_bundle.json"
BUNDLE_FILE_PATHS = (
    "SKILL.md",
    "references/card-behavior-policy.md",
    "references/contract-compiler-checklist.md",
    "references/globalvalues-policy.md",
    "references/guide-research-policy.md",
    "references/visionai-surfaces.md",
    "references/workflow.md",
    "scripts/build_config.py",
    "scripts/validate_package.py",
)
_ROOT_FIELDS = frozenset(
    {"schema_version", "bundle_name", "aggregate_sha256", "files"}
)
_FILE_FIELDS = frozenset({"path", "size", "sha256", "content"})
_MAX_BUNDLE_BYTES = 1_048_576
_MAX_FILE_BYTES = 524_288
_MAX_JOURNAL_BYTES = 16_384
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[/\\]")
_RESERVED_NAMES = {
    "aux",
    "clock$",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "con",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
    "nul",
    "prn",
}
_TRANSACTION_PREFIX = ".hsconfig-install-"
_INSTALL_LOCK_NAME = ".hsconfig-skill-install.lock"
_TRANSACTION_JOURNAL_NAME = re.compile(
    r"^\.hsconfig-install-(?P<transaction_id>[0-9a-f]{32})\.journal\.json$"
)
_PREPARED_JOURNAL_FIELDS = frozenset(
    {
        "schema_version",
        "transaction_id",
        "destination",
        "phase",
        "predecessor_present",
        "predecessor_tree_sha256",
        "predecessor_root_identity",
        "successor_bundle_sha256",
        "successor_tree_sha256",
        "staging_name",
        "backup_name",
    }
)
_COMMITTED_JOURNAL_FIELDS = _PREPARED_JOURNAL_FIELDS | frozenset(
    {
        "successor_root_identity",
        "backup_root_identity",
        "cleanup_entries",
        "cleanup_inventory_sha256",
        "cleanup_cursor",
    }
)
_CLEANUP_NONFILE_ENTRY_FIELDS = frozenset({"kind", "path", "identity"})
_CLEANUP_FILE_ENTRY_FIELDS = _CLEANUP_NONFILE_ENTRY_FIELDS | frozenset(
    {"size", "sha256"}
)


class BundleValidationError(ValueError):
    """Raised when embedded bundle bytes are not canonical and self-consistent."""


def compute_bundle_aggregate(files: Mapping[str, bytes]) -> str:
    """Return the path-byte-sorted digest for one logical bundle inventory."""
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda value: value.encode("utf-8")):
        content = files[path]
        content_digest = hashlib.sha256(content).hexdigest()
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content_digest.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def decode_skill_bundle(raw: bytes) -> dict[str, bytes]:
    """Decode closed JSON bytes into a validated logical skill file mapping."""
    if not isinstance(raw, bytes):
        raise TypeError("bundle_bytes_required")
    if len(raw) > _MAX_BUNDLE_BYTES:
        raise BundleValidationError("bundle_oversize")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise BundleValidationError("bundle_bom")
    if b"\x00" in raw:
        raise BundleValidationError("bundle_nul")
    if b"\r" in raw:
        raise BundleValidationError("bundle_bare_cr")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise BundleValidationError("bundle_invalid_utf8") from error
    try:
        document = json.loads(
            text,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_nonfinite,
        )
    except BundleValidationError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise BundleValidationError("bundle_invalid_json") from error
    if not isinstance(document, dict) or set(document) != _ROOT_FIELDS:
        raise BundleValidationError("bundle_root_schema")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise BundleValidationError("bundle_schema_version")
    if document["bundle_name"] != "hsconfig":
        raise BundleValidationError("bundle_name")
    aggregate = document["aggregate_sha256"]
    if not isinstance(aggregate, str) or _HEX_SHA256.fullmatch(aggregate) is None:
        raise BundleValidationError("bundle_aggregate_schema")
    rows = document["files"]
    if not isinstance(rows, list) or len(rows) != len(BUNDLE_FILE_PATHS):
        raise BundleValidationError("bundle_inventory_schema")

    decoded: dict[str, bytes] = {}
    casefold_paths: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != _FILE_FIELDS:
            raise BundleValidationError("bundle_file_schema")
        path = row["path"]
        if not isinstance(path, str):
            raise BundleValidationError("bundle_path_schema")
        _validate_bundle_path(path)
        folded = unicodedata.normalize("NFC", path).casefold()
        if previous := casefold_paths.get(folded):
            raise BundleValidationError(
                f"bundle_path_casefold_collision:{previous}:{path}"
            )
        casefold_paths[folded] = path
        if path in decoded:
            raise BundleValidationError(f"bundle_path_duplicate:{path}")
        content = row["content"]
        if not isinstance(content, str):
            raise BundleValidationError(f"bundle_content_schema:{path}")
        try:
            content_bytes = content.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise BundleValidationError(f"bundle_content_invalid_utf8:{path}") from error
        _validate_content_bytes(path, content_bytes)
        size = row["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise BundleValidationError(f"bundle_size_schema:{path}")
        if size != len(content_bytes):
            raise BundleValidationError(f"bundle_size_mismatch:{path}")
        expected_hash = row["sha256"]
        if (
            not isinstance(expected_hash, str)
            or _HEX_SHA256.fullmatch(expected_hash) is None
            or hashlib.sha256(content_bytes).hexdigest() != expected_hash
        ):
            raise BundleValidationError(f"bundle_hash_mismatch:{path}")
        decoded[path] = content_bytes

    if tuple(decoded) != BUNDLE_FILE_PATHS:
        raise BundleValidationError("bundle_inventory_order")
    if compute_bundle_aggregate(decoded) != aggregate:
        raise BundleValidationError("bundle_aggregate_mismatch")
    _external_skill_tree_aggregate(decoded, _expected_bundle_directories(decoded))
    _validate_skill_contract(decoded)
    return decoded


def load_embedded_skill_bundle() -> dict[str, bytes]:
    """Read and validate the package-owned skill resource without installing it."""
    raw = (
        resources.files("hsconfig")
        .joinpath("resources", BUNDLE_RESOURCE_NAME)
        .read_bytes()
    )
    return decode_skill_bundle(raw)


@dataclass(frozen=True, slots=True)
class _ExternalSkillTreeObservation:
    present: bool
    aggregate_sha256: str | None
    root_identity: tuple[int, int, int] | None
    files: int
    directories: int


def _external_skill_tree_aggregate(
    files: Mapping[str, bytes],
    directories: Sequence[str],
) -> str:
    rows = [
        *((path, "directory", None) for path in directories),
        *((path, "file", content) for path, content in files.items()),
    ]
    _validate_closed_tree_paths((path for path, _kind, _content in rows))
    digest = hashlib.sha256(b"hsconfig-external-skill-tree-v1\0")
    for path, kind, content in sorted(
        rows,
        key=lambda row: row[0].encode("utf-8"),
    ):
        _validate_bundle_path(path)
        digest.update(b"D\0" if kind == "directory" else b"F\0")
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        if content is not None:
            digest.update(str(len(content)).encode("ascii"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(content).hexdigest().encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest()


def _validate_closed_tree_paths(paths: Iterable[str]) -> None:
    seen: dict[str, str] = {}
    for raw in paths:
        if not isinstance(raw, str):
            raise ValueError("external_skill_tree_path_invalid")
        folded = unicodedata.normalize("NFC", raw).casefold()
        previous = seen.get(folded)
        if previous is not None:
            raise ValueError(f"external_skill_tree_path_collision:{previous}:{raw}")
        seen[folded] = raw
        _validate_bundle_path(raw)


def _expected_bundle_directories(files: Mapping[str, bytes]) -> tuple[str, ...]:
    directories: set[str] = set()
    for relative in files:
        parts = PurePosixPath(relative).parts[:-1]
        for length in range(1, len(parts) + 1):
            directories.add(PurePosixPath(*parts[:length]).as_posix())
    return tuple(sorted(directories))


def _observe_external_skill_tree(target: Path) -> _ExternalSkillTreeObservation:
    if not path_lexists(target):
        return _ExternalSkillTreeObservation(False, None, None, 0, 0)
    require_plain_directory(target)
    root_identity = path_identity(target)
    snapshot = snapshot_bounded_filesystem_package(target)
    files = {
        relative: snapshot.read_bytes(relative)
        for relative in snapshot.file_names()
    }
    directories = snapshot.directory_names
    aggregate_sha256 = _external_skill_tree_aggregate(files, directories)
    require_no_alternate_data_streams(
        target,
        expected_identity=root_identity,
        expected_parent_identity=path_identity(target.parent),
        directory=True,
    )
    for relative in snapshot.directory_names:
        directory = target / relative
        require_no_alternate_data_streams(
            directory,
            expected_identity=path_identity(directory),
            expected_parent_identity=path_identity(directory.parent),
            directory=True,
        )
    for relative in snapshot.file_names():
        file_path = target / relative
        status = plain_file_status(file_path)
        require_no_alternate_data_streams(
            file_path,
            expected_identity=path_identity_from_status(status),
            expected_parent_identity=path_identity(file_path.parent),
            directory=False,
            expected_size=status.st_size,
        )
    if path_identity(target) != root_identity:
        raise ValueError("external_skill_destination_changed")
    return _ExternalSkillTreeObservation(
        True,
        aggregate_sha256,
        root_identity,
        len(files),
        len(directories),
    )


def _require_exact_predecessor_observation(
    root: Path,
    predecessor: _ExternalSkillTreeObservation,
) -> None:
    if _observe_external_skill_tree(root) != predecessor:
        raise ValueError("external_skill_predecessor_tree_changed")


def _require_exact_successor_observation(
    root: Path,
    files: Mapping[str, bytes],
    *,
    root_identity: tuple[int, int, int],
    aggregate_sha256: str,
) -> None:
    observation = _observe_external_skill_tree(root)
    if (
        not observation.present
        or observation.root_identity != root_identity
        or observation.aggregate_sha256 != aggregate_sha256
        or observation.files != len(files)
        or observation.directories != len(_expected_bundle_directories(files))
    ):
        raise ValueError("external_skill_committed_target_changed")
    _assert_materialized_bundle(root, files)


def external_skill_tree_identity(destination: Path) -> dict[str, object]:
    """Return a closed read-only identity a controller can review and bind later."""
    target, _parent = _validate_install_destination(destination)
    observation = _observe_external_skill_tree(target)
    return {
        "schema_version": 1,
        "present": observation.present,
        "aggregate_sha256": observation.aggregate_sha256,
        "files": observation.files,
        "directories": observation.directories,
    }


def install_external_skill(
    destination: Path,
    *,
    expected_predecessor_aggregate_sha256: str | None,
    fault_hook: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Explicitly replace one Windows skill directory from the embedded bundle."""
    if os.name != "nt":
        raise OSError("external_skill_install_requires_windows")
    if expected_predecessor_aggregate_sha256 is not None and (
        not isinstance(expected_predecessor_aggregate_sha256, str)
        or _HEX_SHA256.fullmatch(expected_predecessor_aggregate_sha256) is None
    ):
        raise ValueError("external_skill_predecessor_aggregate_schema")
    target, parent = _validate_install_destination(destination)
    files = load_embedded_skill_bundle()
    successor_tree_sha256 = _external_skill_tree_aggregate(
        files,
        _expected_bundle_directories(files),
    )
    hook = fault_hook or _no_fault
    prelock = _observe_external_skill_tree(target)
    _require_expected_predecessor(
        prelock,
        expected_predecessor_aggregate_sha256,
        successor_tree_sha256=successor_tree_sha256,
    )
    parent_identity = path_identity(parent)
    hook("after_prelock_snapshot")
    lock_path = parent / _INSTALL_LOCK_NAME
    with ExclusiveFileLock(
        lock_path,
        expected_parent_identity=parent_identity,
    ):
        _require_directory_identity(parent, parent_identity)
        hook("after_lock_before_predecessor_recheck")
        locked_target, locked_parent = _validate_install_destination(target)
        if locked_target != target or locked_parent != parent:
            raise ValueError("external_skill_destination_changed")
        locked = _observe_external_skill_tree(target)
        if locked != prelock:
            raise ValueError("external_skill_predecessor_changed_under_lock")
        _require_expected_predecessor(
            locked,
            expected_predecessor_aggregate_sha256,
            successor_tree_sha256=successor_tree_sha256,
        )
        _recover_committed_transaction_if_present(
            parent,
            target,
            files,
            parent_identity=parent_identity,
        )
        post_recovery = _observe_external_skill_tree(target)
        if post_recovery != locked:
            raise ValueError("external_skill_predecessor_changed_during_recovery")
        _require_expected_predecessor(
            post_recovery,
            expected_predecessor_aggregate_sha256,
            successor_tree_sha256=successor_tree_sha256,
        )
        if post_recovery.present and post_recovery.aggregate_sha256 == successor_tree_sha256:
            return {
                "aggregate_sha256": compute_bundle_aggregate(files),
                "destination": str(target),
                "files_installed": len(files),
                "status": "already_current",
            }
        return _install_external_skill_locked(
            target,
            parent,
            files,
            parent_identity=parent_identity,
            predecessor=post_recovery,
            successor_tree_sha256=successor_tree_sha256,
            fault_hook=fault_hook,
        )


def _require_expected_predecessor(
    observation: _ExternalSkillTreeObservation,
    expected_aggregate_sha256: str | None,
    *,
    successor_tree_sha256: str,
) -> None:
    if observation.present and observation.aggregate_sha256 == successor_tree_sha256:
        return
    if not observation.present:
        if expected_aggregate_sha256 is None:
            return
        raise ValueError("external_skill_predecessor_missing")
    if (
        expected_aggregate_sha256 is None
        or observation.aggregate_sha256 != expected_aggregate_sha256
    ):
        raise ValueError("external_skill_predecessor_aggregate_mismatch")


def _install_external_skill_locked(
    target: Path,
    parent: Path,
    files: Mapping[str, bytes],
    *,
    parent_identity: tuple[int, int, int],
    predecessor: _ExternalSkillTreeObservation,
    successor_tree_sha256: str,
    fault_hook: Callable[[str], None] | None,
) -> dict[str, object]:
    hook = fault_hook or _no_fault
    _assert_no_transaction_residue(parent)
    aggregate = compute_bundle_aggregate(files)
    transaction_id = uuid.uuid4().hex
    journal = parent / f"{_TRANSACTION_PREFIX}{transaction_id}.journal.json"
    staging = parent / f"{_TRANSACTION_PREFIX}{transaction_id}.stage"
    backup = parent / f"{_TRANSACTION_PREFIX}{transaction_id}.backup"
    original_present = predecessor.present
    original_identity = predecessor.root_identity
    staging_identity: tuple[int, int, int] | None = None
    backup_identity: tuple[int, int, int] | None = None
    rollback_complete = False
    commit_reached = False
    committed_journal: dict[str, object] | None = None
    committed_payload: bytes | None = None
    prepared_journal = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "destination": str(target),
        "phase": "prepared",
        "predecessor_present": predecessor.present,
        "predecessor_tree_sha256": predecessor.aggregate_sha256,
        "predecessor_root_identity": (
            list(predecessor.root_identity)
            if predecessor.root_identity is not None
            else None
        ),
        "successor_bundle_sha256": aggregate,
        "successor_tree_sha256": successor_tree_sha256,
        "staging_name": staging.name,
        "backup_name": backup.name,
    }

    try:
        _write_new_journal(
            journal,
            prepared_journal,
            parent_identity=parent_identity,
            fault_hook=hook,
        )
        hook("after_journal_create")
        _require_directory_identity(parent, parent_identity)
        staging_identity = secure_create_directory(
            staging,
            expected_parent_identity=parent_identity,
        )
        hook("after_stage_create")
        _materialize_bundle(staging, files)
        _assert_materialized_bundle(staging, files)
        hook("after_stage_write")
        _require_directory_identity(parent, parent_identity)
        current_predecessor = _observe_external_skill_tree(target)
        if current_predecessor != predecessor:
            raise ValueError("external_skill_predecessor_changed_before_replace")
        cleanup_entries = (
            _capture_backup_cleanup_entries(target, predecessor)
            if original_present
            else []
        )
        committed_journal = {
            **prepared_journal,
            "phase": "committed",
            "successor_root_identity": list(staging_identity),
            "backup_root_identity": (
                list(original_identity) if original_identity is not None else None
            ),
            "cleanup_entries": cleanup_entries,
            "cleanup_inventory_sha256": _cleanup_inventory_sha256(cleanup_entries),
            "cleanup_cursor": 0,
        }
        committed_payload = _journal_bytes(committed_journal)
        if original_present:
            hook("before_destination_backup")
            if _observe_external_skill_tree(target) != predecessor:
                raise ValueError("external_skill_predecessor_changed_before_backup")
            secure_replace(
                target,
                backup,
                expected_source_identity=original_identity,
                expected_source_parent_identity=parent_identity,
                expected_target_parent_identity=parent_identity,
                expected_target_absent=True,
            )
            backup_identity = original_identity
            hook("after_destination_backup")
        elif _observe_external_skill_tree(target) != predecessor:
            raise ValueError("external_skill_predecessor_changed_before_promote")
        hook("before_destination_promote")
        secure_replace(
            staging,
            target,
            expected_source_identity=staging_identity,
            expected_source_parent_identity=parent_identity,
            expected_target_parent_identity=parent_identity,
            expected_target_absent=True,
        )
        hook("after_destination_promote")
        _require_directory_identity(parent, parent_identity)
        _assert_materialized_bundle(target, files)
        hook("after_verify")
        hook("before_commit")
        if original_present and _capture_backup_cleanup_entries(
            backup,
            predecessor,
        ) != cleanup_entries:
            raise ValueError("external_skill_backup_cleanup_inventory_mismatch")
        _replace_journal(journal, committed_journal)
        commit_reached = True
        hook("after_commit")
        _resume_committed_cleanup(
            journal,
            committed_journal,
            target,
            files,
            parent_identity=parent_identity,
            fault_hook=hook,
        )
        return {
            "aggregate_sha256": aggregate,
            "destination": str(target),
            "files_installed": len(files),
            "status": "installed",
        }
    except BaseException as primary:
        durable_commit = False
        journal_ambiguous = False
        try:
            if path_lexists(journal):
                raw_journal = _read_owned_file(journal)
                if raw_journal == _journal_bytes(prepared_journal):
                    durable_commit = False
                elif committed_payload is not None and raw_journal == committed_payload:
                    durable_commit = True
                else:
                    journal_ambiguous = True
        except BaseException as journal_error:
            journal_ambiguous = True
            _add_note(primary, f"external skill journal read failed: {journal_error!r}")
        if commit_reached or durable_commit:
            try:
                _assert_materialized_bundle(target, files)
            except BaseException as verification_error:
                _add_note(
                    primary,
                    "external skill committed target verification failed: "
                    f"{verification_error!r}",
                )
            raise
        if journal_ambiguous:
            _add_note(primary, "external skill journal state is ambiguous; no rollback run")
            raise
        try:
            promoted = (
                staging_identity is not None
                and path_lexists(target)
                and path_identity(target) == staging_identity
            )
            if promoted:
                _require_exact_successor_observation(
                    target,
                    files,
                    root_identity=staging_identity,
                    aggregate_sha256=successor_tree_sha256,
                )
                if original_present:
                    _require_exact_predecessor_observation(backup, predecessor)
                _remove_owned_tree(target, staging_identity, files)
            if original_present and path_lexists(backup):
                _require_exact_predecessor_observation(backup, predecessor)
                secure_replace(
                    backup,
                    target,
                    expected_source_identity=backup_identity,
                    expected_source_parent_identity=parent_identity,
                    expected_target_parent_identity=parent_identity,
                    expected_target_absent=True,
                )
            if path_lexists(staging):
                if staging_identity is None:
                    raise ValueError("external_skill_stage_identity_missing")
                _remove_owned_tree(staging, staging_identity, files)
            if _observe_external_skill_tree(target) != predecessor:
                raise ValueError("external_skill_predecessor_rollback_mismatch")
            rollback_complete = not path_lexists(backup) and not path_lexists(staging)
            if rollback_complete and path_lexists(journal):
                _delete_owned_file(journal, parent_identity)
        except BaseException as cleanup_error:
            _add_note(primary, f"external skill rollback failed: {cleanup_error!r}")
        raise
    finally:
        if rollback_complete and path_lexists(staging):
            try:
                if staging_identity is not None:
                    _remove_owned_tree(staging, staging_identity, files)
            except BaseException:
                pass


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BundleValidationError(f"bundle_duplicate_key:{key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> object:
    raise BundleValidationError(f"bundle_nonfinite_number:{value}")


def _validate_bundle_path(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise BundleValidationError("bundle_path_schema")
    if unicodedata.normalize("NFC", value) != value:
        raise BundleValidationError(f"bundle_path_not_nfc:{value}")
    if (
        value.startswith(("/", "//"))
        or _WINDOWS_ABSOLUTE.match(value)
        or "\\" in value
    ):
        raise BundleValidationError(f"bundle_path_absolute_or_noncanonical:{value}")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise BundleValidationError(f"bundle_path_traversal:{value}")
    for part in parts:
        if (
            ":" in part
            or part.rstrip(" .") != part
            or any(ord(character) < 32 or ord(character) == 127 for character in part)
        ):
            raise BundleValidationError(f"bundle_path_unsafe_component:{value}")
        if part.split(".", 1)[0].casefold() in _RESERVED_NAMES:
            raise BundleValidationError(f"bundle_path_reserved:{value}")
    if PurePosixPath(value).as_posix() != value:
        raise BundleValidationError(f"bundle_path_noncanonical:{value}")


def _validate_content_bytes(path: str, content: bytes) -> None:
    if len(content) > _MAX_FILE_BYTES:
        raise BundleValidationError(f"bundle_content_oversize:{path}")
    if content.startswith(b"\xef\xbb\xbf"):
        raise BundleValidationError(f"bundle_content_bom:{path}")
    if b"\x00" in content:
        raise BundleValidationError(f"bundle_content_nul:{path}")
    if b"\r" in content:
        raise BundleValidationError(f"bundle_content_bare_cr:{path}")


class _SkillFrontmatterLoader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        self._frontmatter_nodes = 0
        self._frontmatter_depth = 0
        super().__init__(stream)

    def compose_node(
        self,
        parent: yaml.nodes.Node | None,
        index: int | None,
    ) -> yaml.nodes.Node:
        event = self.peek_event()
        if isinstance(event, yaml.events.AliasEvent) or getattr(event, "anchor", None):
            raise ConstructorError(None, None, "anchors and aliases are forbidden", None)
        if getattr(event, "tag", None) is not None:
            raise ConstructorError(None, None, "explicit tags are forbidden", None)
        self._frontmatter_nodes += 1
        self._frontmatter_depth += 1
        if self._frontmatter_nodes > 128 or self._frontmatter_depth > 16:
            raise ConstructorError(None, None, "frontmatter bounds exceeded", None)
        try:
            return super().compose_node(parent, index)
        finally:
            self._frontmatter_depth -= 1


def _construct_skill_frontmatter_mapping(
    loader: _SkillFrontmatterLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[str, object]:
    if not isinstance(node, yaml.nodes.MappingNode):
        raise ConstructorError(None, None, "frontmatter must be a mapping", node.start_mark)
    result: dict[str, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if type(key) is not str:
            raise ConstructorError(None, None, "frontmatter key must be text", key_node.start_mark)
        normalized = unicodedata.normalize("NFC", key.strip()).casefold()
        identities = {
            unicodedata.normalize("NFC", existing.strip()).casefold()
            for existing in result
        }
        if not normalized or normalized in identities:
            raise ConstructorError(None, None, "duplicate frontmatter key", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_SkillFrontmatterLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_skill_frontmatter_mapping,
)


def _load_skill_frontmatter(value: str) -> dict[str, object]:
    if len(value.encode("utf-8")) > 16_384:
        raise BundleValidationError("bundle_skill_frontmatter")
    loader: _SkillFrontmatterLoader | None = None
    try:
        loader = _SkillFrontmatterLoader(value)
        document = loader.get_single_data()
    except (yaml.YAMLError, UnicodeError, RecursionError, MemoryError) as error:
        raise BundleValidationError("bundle_skill_frontmatter") from error
    finally:
        if loader is not None:
            loader.dispose()
    if type(document) is not dict or set(document) != {"name", "description"}:
        raise BundleValidationError("bundle_skill_frontmatter")
    if document["name"] != "hsconfig":
        raise BundleValidationError("bundle_skill_frontmatter")
    description = document["description"]
    if type(description) is not str or not description.strip():
        raise BundleValidationError("bundle_skill_frontmatter")
    return document


def _validate_skill_contract(files: Mapping[str, bytes]) -> None:
    skill = files["SKILL.md"].decode("utf-8")
    if len(skill.encode("utf-8")) < 1_000:
        raise BundleValidationError("bundle_skill_thin_router")
    if not skill.startswith("---\n") or "\n---\n" not in skill[4:]:
        raise BundleValidationError("bundle_skill_frontmatter")
    frontmatter, _separator, body = skill[4:].partition("\n---\n")
    _load_skill_frontmatter(frontmatter)
    if "# HSConfig" not in body:
        raise BundleValidationError("bundle_skill_frontmatter")
    if "## Hard Boundaries" not in body or "## References:" not in body:
        raise BundleValidationError("bundle_skill_thin_router")
    for reference in BUNDLE_FILE_PATHS[1:7]:
        if reference not in skill:
            raise BundleValidationError(
                f"bundle_skill_thin_router_missing:{reference}"
            )
    _validate_markdown_links(files)
    for path in BUNDLE_FILE_PATHS[-2:]:
        try:
            compile(files[path], path, "exec", dont_inherit=True)
        except (SyntaxError, ValueError, TypeError) as error:
            raise BundleValidationError(f"bundle_script_compile:{path}") from error


def _validate_markdown_links(files: Mapping[str, bytes]) -> None:
    for path, content in files.items():
        if not path.endswith(".md"):
            continue
        text = content.decode("utf-8")
        try:
            scan = _scan_markdown_document(text)
        except PublishableTreeError as error:
            raise BundleValidationError(f"bundle_markdown_parse:{path}") from error
        if scan.undefined_references:
            raise BundleValidationError(
                "bundle_markdown_reference_undefined:"
                f"{path}:{scan.undefined_references[0]}"
            )
        if scan.ambiguous_references:
            raise BundleValidationError(
                "bundle_markdown_reference_ambiguous:"
                f"{path}:{scan.ambiguous_references[0]}"
            )
        for target in dict.fromkeys(scan.targets):
            if not target:
                raise BundleValidationError(f"bundle_markdown_link_unsafe:{path}")
            try:
                split = urlsplit(target)
            except ValueError as error:
                raise BundleValidationError(
                    f"bundle_markdown_link_unsafe:{path}"
                ) from error
            if split.scheme:
                if split.scheme.casefold() not in {"http", "https", "mailto"}:
                    raise BundleValidationError(f"bundle_markdown_link_unsafe:{path}")
                continue
            if split.netloc or "#" in target or "?" in target or ":" in target:
                raise BundleValidationError(f"bundle_markdown_link_unsafe:{path}")
            candidate = PurePosixPath(path).parent.joinpath(target)
            normalized = _normalize_bundle_link(candidate)
            if normalized not in files:
                raise BundleValidationError(
                    f"bundle_markdown_link_missing:{path}:{target}"
                )


def _normalize_bundle_link(path: PurePosixPath) -> str:
    parts: list[str] = []
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise BundleValidationError("bundle_markdown_link_traversal")
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _validate_install_destination(destination: Path) -> tuple[Path, Path]:
    if not isinstance(destination, Path):
        raise TypeError("external_skill_destination_path_required")
    if not destination.is_absolute():
        raise ValueError("external_skill_destination_absolute_required")
    target = Path(os.path.abspath(destination))
    if target.name != "hsconfig":
        raise ValueError("external_skill_destination_name")
    _validate_bundle_path(target.name)
    parent = target.parent
    _validate_existing_directory_chain(parent)
    if path_lexists(target):
        _validate_existing_tree(target)
    return target, parent


def _validate_existing_directory_chain(path: Path) -> None:
    chain = [path, *path.parents]
    for node in reversed(chain):
        if not path_lexists(node):
            raise ValueError(f"external_skill_parent_missing:{node}")
        node_stat = os.lstat(node)
        if (
            not stat.S_ISDIR(node_stat.st_mode)
            or stat.S_ISLNK(node_stat.st_mode)
            or _is_reparse(node_stat)
        ):
            raise ValueError(f"external_skill_parent_unsafe:{node}")


def _validate_existing_tree(root: Path) -> None:
    try:
        require_plain_directory(root)
        snapshot_bounded_filesystem_package(root)
    except (OSError, ValueError) as error:
        raise ValueError(f"external_skill_destination_unsafe:{root}") from error


def _assert_no_transaction_residue(parent: Path) -> None:
    for path in parent.iterdir():
        if path.name.startswith(_TRANSACTION_PREFIX):
            raise ValueError(f"external_skill_transaction_residue:{path.name}")


def _write_new_journal(
    path: Path,
    value: Mapping[str, object],
    *,
    parent_identity: tuple[int, int, int],
    fault_hook: Callable[[str], None],
) -> None:
    payload = _journal_bytes(value)
    temp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor: int | None = None
    temp_identity: tuple[int, int, int] | None = None
    try:
        descriptor, temp_identity = _open_owned_journal_temp(
            temp,
            parent_identity=parent_identity,
        )
        fault_hook("after_journal_temp_create")
        _write_all(descriptor, payload)
        fault_hook("after_journal_temp_write")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        fault_hook("after_journal_temp_flush")
        fault_hook("before_journal_publish")
        secure_replace(
            temp,
            path,
            expected_source_identity=temp_identity,
            expected_source_parent_identity=parent_identity,
            expected_target_parent_identity=parent_identity,
            expected_target_absent=True,
        )
        temp_identity = None
        fault_hook("after_journal_publish")
    except BaseException as primary:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except BaseException as close_error:
                _add_note(primary, f"external skill journal temp close failed: {close_error!r}")
        if temp_identity is not None and path_lexists(temp):
            try:
                secure_unlink(
                    temp,
                    expected_identity=temp_identity,
                    expected_parent_identity=parent_identity,
                )
            except BaseException as cleanup_error:
                _add_note(
                    primary,
                    f"external skill journal temp cleanup failed: {cleanup_error!r}",
                )
        raise
    if _read_owned_file(path) != payload:
        raise ValueError("external_skill_journal_write_mismatch")


def _open_owned_journal_temp(
    path: Path,
    *,
    parent_identity: tuple[int, int, int],
) -> tuple[int, tuple[int, int, int]]:
    descriptor = secure_open_file_descriptor(
        path,
        create=True,
        write=True,
        expected_parent_identity=parent_identity,
    )
    owned_identity: tuple[int, int, int] | None = None
    try:
        owned_identity = _journal_descriptor_identity(descriptor)
        if path_identity_from_status(plain_file_status(path)) != owned_identity:
            raise ValueError("external_skill_journal_temp_identity_changed")
        return descriptor, owned_identity
    except BaseException as primary:
        if owned_identity is None:
            try:
                owned_identity = path_identity_from_status(os.fstat(descriptor))
            except BaseException as identity_error:
                _add_note(
                    primary,
                    f"external skill journal temp identity recovery failed: {identity_error!r}",
                )
        try:
            os.close(descriptor)
        except BaseException as close_error:
            _add_note(primary, f"external skill journal temp close failed: {close_error!r}")
        if owned_identity is not None and path_lexists(path):
            try:
                secure_unlink(
                    path,
                    expected_identity=owned_identity,
                    expected_parent_identity=parent_identity,
                )
            except BaseException as cleanup_error:
                _add_note(
                    primary,
                    f"external skill journal temp cleanup failed: {cleanup_error!r}",
                )
        raise


def _journal_descriptor_identity(descriptor: int) -> tuple[int, int, int]:
    return path_identity_from_status(os.fstat(descriptor))


def _replace_journal(path: Path, value: Mapping[str, object]) -> None:
    payload = _journal_bytes(value)
    atomic_write_bytes(path, payload)
    if _read_owned_file(path) != payload:
        raise ValueError("external_skill_journal_commit_mismatch")


def _journal_bytes(value: Mapping[str, object]) -> bytes:
    payload = (
        json.dumps(
            dict(value),
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if len(payload) > _MAX_JOURNAL_BYTES:
        raise ValueError("external_skill_journal_oversize")
    return payload


def _read_owned_file(path: Path) -> bytes:
    status = plain_file_status(path)
    return read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=_MAX_JOURNAL_BYTES,
    )


def _load_transaction_journal(path: Path) -> dict[str, object]:
    try:
        document = json.loads(
            _read_owned_file(path).decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_nonfinite,
        )
    except (BundleValidationError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("external_skill_journal_invalid") from error
    if not isinstance(document, dict):
        raise ValueError("external_skill_journal_invalid")
    return document


def _capture_backup_cleanup_entries(
    backup: Path,
    predecessor: _ExternalSkillTreeObservation,
) -> list[dict[str, object]]:
    observed = _observe_external_skill_tree(backup)
    if (
        not predecessor.present
        or observed.aggregate_sha256 != predecessor.aggregate_sha256
        or observed.root_identity != predecessor.root_identity
    ):
        raise ValueError("external_skill_backup_predecessor_mismatch")
    snapshot = snapshot_bounded_filesystem_package(backup)
    snapshot_files = {
        name: snapshot.read_bytes(name)
        for name in snapshot.file_names()
    }
    if (
        _external_skill_tree_aggregate(snapshot_files, snapshot.directory_names)
        != predecessor.aggregate_sha256
        or path_identity(backup) != predecessor.root_identity
    ):
        raise ValueError("external_skill_backup_predecessor_mismatch")
    entries: list[dict[str, object]] = []
    for name in sorted(
        snapshot.file_names(),
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        content = snapshot_files[name]
        entries.append(
            {
                "kind": "file",
                "path": name,
                "identity": list(path_identity_from_status(plain_file_status(backup / name))),
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    for name in sorted(
        snapshot.directory_names,
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        entries.append(
            {
                "kind": "directory",
                "path": name,
                "identity": list(path_identity(backup / name)),
            }
        )
    if predecessor.root_identity is None:
        raise ValueError("external_skill_backup_predecessor_mismatch")
    entries.append(
        {
            "kind": "root",
            "path": "",
            "identity": list(predecessor.root_identity),
        }
    )
    return entries


def _cleanup_inventory_sha256(entries: Sequence[Mapping[str, object]]) -> str:
    payload = json.dumps(
        [dict(entry) for entry in entries],
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(b"hsconfig-external-skill-cleanup-v1\0" + payload).hexdigest()


def _identity_from_json(value: object, *, field: str) -> tuple[int, int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(part) is not int for part in value)
    ):
        raise ValueError(f"external_skill_journal_identity_invalid:{field}")
    return value[0], value[1], value[2]


def _validated_cleanup_entries(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError("external_skill_journal_cleanup_invalid")
    entries: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError("external_skill_journal_cleanup_invalid")
        kind = raw["kind"]
        path = raw["path"]
        if kind not in {"file", "directory", "root"} or not isinstance(path, str):
            raise ValueError("external_skill_journal_cleanup_invalid")
        expected_fields = (
            _CLEANUP_FILE_ENTRY_FIELDS
            if kind == "file"
            else _CLEANUP_NONFILE_ENTRY_FIELDS
        )
        if set(raw) != expected_fields:
            raise ValueError("external_skill_journal_cleanup_invalid")
        if kind == "root":
            if path != "" or index != len(value) - 1:
                raise ValueError("external_skill_journal_cleanup_invalid")
        else:
            _validate_bundle_path(path)
        key = str(kind), path
        if key in seen:
            raise ValueError("external_skill_journal_cleanup_invalid")
        seen.add(key)
        identity = _identity_from_json(raw["identity"], field=f"cleanup:{index}")
        entry: dict[str, object] = {
            "kind": kind,
            "path": path,
            "identity": list(identity),
        }
        if kind == "file":
            size = raw["size"]
            content_sha256 = raw["sha256"]
            if (
                type(size) is not int
                or size < 0
                or size > MAX_RUN_TOTAL_BYTES
                or not isinstance(content_sha256, str)
                or _HEX_SHA256.fullmatch(content_sha256) is None
            ):
                raise ValueError("external_skill_journal_cleanup_invalid")
            entry["size"] = size
            entry["sha256"] = content_sha256
        entries.append(entry)
    _validate_closed_tree_paths(
        str(entry["path"]) for entry in entries if entry["kind"] != "root"
    )
    return entries


def _validate_committed_journal(
    document: Mapping[str, object],
    journal: Path,
    target: Path,
    files: Mapping[str, bytes],
) -> list[dict[str, object]]:
    match = _TRANSACTION_JOURNAL_NAME.fullmatch(journal.name)
    if match is None or set(document) != _COMMITTED_JOURNAL_FIELDS:
        raise ValueError("external_skill_committed_journal_invalid")
    transaction_id = match.group("transaction_id")
    successor_tree_sha256 = _external_skill_tree_aggregate(
        files,
        _expected_bundle_directories(files),
    )
    predecessor_present = document["predecessor_present"]
    predecessor_sha256 = document["predecessor_tree_sha256"]
    predecessor_identity = document["predecessor_root_identity"]
    backup_identity = document["backup_root_identity"]
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["transaction_id"] != transaction_id
        or document["destination"] != str(target)
        or document["phase"] != "committed"
        or type(predecessor_present) is not bool
        or document["successor_bundle_sha256"] != compute_bundle_aggregate(files)
        or document["successor_tree_sha256"] != successor_tree_sha256
        or document["staging_name"] != f"{_TRANSACTION_PREFIX}{transaction_id}.stage"
        or document["backup_name"] != f"{_TRANSACTION_PREFIX}{transaction_id}.backup"
    ):
        raise ValueError("external_skill_committed_journal_invalid")
    if predecessor_present:
        if (
            not isinstance(predecessor_sha256, str)
            or _HEX_SHA256.fullmatch(predecessor_sha256) is None
            or _identity_from_json(
                predecessor_identity,
                field="predecessor_root_identity",
            )
            != _identity_from_json(backup_identity, field="backup_root_identity")
        ):
            raise ValueError("external_skill_committed_journal_invalid")
    elif predecessor_sha256 is not None or predecessor_identity is not None or backup_identity is not None:
        raise ValueError("external_skill_committed_journal_invalid")
    successor_identity = _identity_from_json(
        document["successor_root_identity"],
        field="successor_root_identity",
    )
    _require_exact_successor_observation(
        target,
        files,
        root_identity=successor_identity,
        aggregate_sha256=successor_tree_sha256,
    )
    entries = _validated_cleanup_entries(document["cleanup_entries"])
    if predecessor_present != bool(entries):
        raise ValueError("external_skill_committed_journal_invalid")
    if document["cleanup_inventory_sha256"] != _cleanup_inventory_sha256(entries):
        raise ValueError("external_skill_committed_journal_invalid")
    cursor = document["cleanup_cursor"]
    if type(cursor) is not int or cursor < 0 or cursor > len(entries):
        raise ValueError("external_skill_committed_journal_invalid")
    return entries


def _recover_committed_transaction_if_present(
    parent: Path,
    target: Path,
    files: Mapping[str, bytes],
    *,
    parent_identity: tuple[int, int, int],
) -> None:
    residue = sorted(
        (path for path in parent.iterdir() if path.name.startswith(_TRANSACTION_PREFIX)),
        key=lambda path: path.name,
    )
    if not residue:
        return
    journals = [path for path in residue if _TRANSACTION_JOURNAL_NAME.fullmatch(path.name)]
    if len(journals) != 1:
        raise ValueError("external_skill_transaction_residue_unclassified")
    journal = journals[0]
    document = _load_transaction_journal(journal)
    if document.get("phase") != "committed":
        raise ValueError("external_skill_transaction_not_committed")
    entries = _validate_committed_journal(document, journal, target, files)
    allowed = {journal.name, str(document["backup_name"])}
    if any(path.name not in allowed for path in residue):
        raise ValueError("external_skill_transaction_residue_unclassified")
    _resume_committed_cleanup(
        journal,
        {**document, "cleanup_entries": entries},
        target,
        files,
        parent_identity=parent_identity,
        fault_hook=_no_fault,
    )


def _cleanup_state_matches(
    backup: Path,
    backup_identity: tuple[int, int, int] | None,
    entries: Sequence[Mapping[str, object]],
    cursor: int,
) -> bool:
    remaining = entries[cursor:]
    if not path_lexists(backup):
        return not remaining
    if backup_identity is None or path_identity(backup) != backup_identity:
        return False
    snapshot = snapshot_bounded_filesystem_package(backup)
    expected_members = {
        (str(entry["kind"]), str(entry["path"])): _identity_from_json(
            entry["identity"],
            field=f"cleanup:{index}",
        )
        for index, entry in enumerate(remaining, start=cursor)
        if entry["kind"] != "root"
    }
    actual_members = {
        *(('file', name) for name in snapshot.file_names()),
        *(('directory', name) for name in snapshot.directory_names),
    }
    if set(expected_members) != actual_members:
        return False
    for (kind, name), identity in expected_members.items():
        path = backup / name
        actual = (
            path_identity_from_status(plain_file_status(path))
            if kind == "file"
            else path_identity(path)
        )
        if actual != identity:
            return False
        if kind == "file":
            entry = next(
                row
                for row in remaining
                if row["kind"] == "file" and row["path"] == name
            )
            content = snapshot.read_bytes(name)
            if (
                len(content) != entry["size"]
                or hashlib.sha256(content).hexdigest() != entry["sha256"]
            ):
                return False
    return True


def _delete_cleanup_entry(
    backup: Path,
    entry: Mapping[str, object],
    *,
    parent_identity: tuple[int, int, int],
) -> None:
    kind = str(entry["kind"])
    relative = str(entry["path"])
    identity = _identity_from_json(entry["identity"], field="cleanup_entry")
    path = backup if kind == "root" else backup / relative
    if kind == "file":
        try:
            secure_unlink_verified(
                path,
                expected_identity=identity,
                expected_parent_identity=path_identity(path.parent),
                expected_size=int(entry["size"]),
                expected_sha256=str(entry["sha256"]),
            )
        except (OSError, ValueError) as error:
            raise ValueError("external_skill_cleanup_file_changed") from error
    elif kind == "directory":
        try:
            secure_rmdir_verified(
                path,
                expected_identity=identity,
                expected_parent_identity=path_identity(path.parent),
            )
        except (OSError, ValueError) as error:
            raise ValueError("external_skill_cleanup_directory_changed") from error
    elif kind == "root":
        try:
            secure_rmdir_verified(
                path,
                expected_identity=identity,
                expected_parent_identity=parent_identity,
            )
        except (OSError, ValueError) as error:
            raise ValueError("external_skill_cleanup_root_changed") from error
    else:
        raise ValueError("external_skill_cleanup_kind_invalid")


def _resume_committed_cleanup(
    journal: Path,
    document: Mapping[str, object],
    target: Path,
    files: Mapping[str, bytes],
    *,
    parent_identity: tuple[int, int, int],
    fault_hook: Callable[[str], None],
) -> None:
    current = dict(document)
    entries = _validate_committed_journal(current, journal, target, files)
    cursor = int(current["cleanup_cursor"])
    backup = journal.parent / str(current["backup_name"])
    backup_identity = (
        _identity_from_json(current["backup_root_identity"], field="backup_root_identity")
        if current["backup_root_identity"] is not None
        else None
    )
    if cursor == 0 and entries and _cleanup_state_matches(
        backup,
        backup_identity,
        entries,
        0,
    ):
        predecessor = _ExternalSkillTreeObservation(
            True,
            str(current["predecessor_tree_sha256"]),
            backup_identity,
            0,
            0,
        )
        if _capture_backup_cleanup_entries(backup, predecessor) != entries:
            raise ValueError("external_skill_backup_cleanup_inventory_mismatch")
    if entries and cursor == 0:
        fault_hook("before_backup_cleanup")
    while cursor < len(entries):
        _require_committed_successor(target, files, current)
        if not _cleanup_state_matches(backup, backup_identity, entries, cursor):
            if _cleanup_state_matches(backup, backup_identity, entries, cursor + 1):
                cursor += 1
                current["cleanup_cursor"] = cursor
                _replace_journal(journal, current)
                continue
            raise ValueError("external_skill_backup_cleanup_state_changed")
        _delete_cleanup_entry(
            backup,
            entries[cursor],
            parent_identity=parent_identity,
        )
        fault_hook("after_backup_cleanup_entry")
        cursor += 1
        current["cleanup_cursor"] = cursor
        _replace_journal(journal, current)
    if not _cleanup_state_matches(backup, backup_identity, entries, cursor):
        raise ValueError("external_skill_backup_cleanup_incomplete")
    if entries:
        fault_hook("after_backup_cleanup")
    _require_committed_successor(target, files, current)
    fault_hook("before_journal_delete")
    _require_committed_successor(target, files, current)
    _delete_owned_file(journal, parent_identity)


def _require_committed_successor(
    target: Path,
    files: Mapping[str, bytes],
    document: Mapping[str, object],
) -> None:
    _require_exact_successor_observation(
        target,
        files,
        root_identity=_identity_from_json(
            document["successor_root_identity"],
            field="successor_root_identity",
        ),
        aggregate_sha256=str(document["successor_tree_sha256"]),
    )


def _materialize_bundle(root: Path, files: Mapping[str, bytes]) -> None:
    for relative, content in files.items():
        path = root.joinpath(*PurePosixPath(relative).parts)
        current = root
        for component in PurePosixPath(relative).parts[:-1]:
            child = current / component
            if not path_lexists(child):
                secure_create_directory(
                    child,
                    expected_parent_identity=path_identity(current),
                )
            else:
                require_plain_directory(child)
            current = child
        descriptor = secure_open_file_descriptor(
            path,
            create=True,
            write=True,
            expected_parent_identity=path_identity(path.parent),
        )
        try:
            _write_all(descriptor, content)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _assert_materialized_bundle(root: Path, expected: Mapping[str, bytes]) -> None:
    snapshot = snapshot_bounded_filesystem_package(root)
    actual = {
        relative: snapshot.read_bytes(relative)
        for relative in snapshot.file_names()
    }
    if (
        actual != dict(expected)
        or snapshot.directory_names != _expected_bundle_directories(expected)
    ):
        raise ValueError("external_skill_materialization_mismatch")


def _remove_owned_tree(
    root: Path,
    expected_identity: tuple[int, int, int],
    expected_files: Mapping[str, bytes],
) -> None:
    require_plain_directory(root)
    if path_identity(root) != expected_identity:
        raise ValueError("external_skill_owned_tree_identity_changed")
    expected_directories = _expected_bundle_directories(expected_files)
    expected_aggregate = _external_skill_tree_aggregate(
        expected_files,
        expected_directories,
    )
    observation = _observe_external_skill_tree(root)
    if (
        observation.root_identity != expected_identity
        or observation.aggregate_sha256 != expected_aggregate
        or observation.files != len(expected_files)
        or observation.directories != len(expected_directories)
    ):
        raise ValueError("external_skill_owned_tree_changed")
    snapshot = snapshot_bounded_filesystem_package(root)
    actual_files = {
        name: snapshot.read_bytes(name)
        for name in snapshot.file_names()
    }
    if actual_files != dict(expected_files) or snapshot.directory_names != expected_directories:
        raise ValueError("external_skill_owned_tree_changed")
    for name in sorted(
        snapshot.file_names(),
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        path = root / Path(name)
        status = plain_file_status(path)
        content = actual_files[name]
        secure_unlink_verified(
            path,
            expected_identity=path_identity_from_status(status),
            expected_parent_identity=path_identity(path.parent),
            expected_size=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )
    for name in sorted(
        snapshot.directory_names,
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        path = root / Path(name)
        secure_rmdir_verified(
            path,
            expected_identity=path_identity(path),
            expected_parent_identity=path_identity(path.parent),
        )
    secure_rmdir_verified(
        root,
        expected_identity=expected_identity,
        expected_parent_identity=path_identity(root.parent),
    )


def _delete_owned_file(path: Path, parent_identity: tuple[int, int, int]) -> None:
    status = plain_file_status(path)
    content = read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=_MAX_JOURNAL_BYTES,
    )
    secure_unlink_verified(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=parent_identity,
        expected_size=len(content),
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )


def _add_note(error: BaseException, note: str) -> None:
    try:
        error.add_note(note)
    except BaseException:
        pass


def _require_directory_identity(
    path: Path,
    identity: tuple[int, int, int],
) -> None:
    node_stat = os.lstat(path)
    if (
        not stat.S_ISDIR(node_stat.st_mode)
        or stat.S_ISLNK(node_stat.st_mode)
        or _is_reparse(node_stat)
        or path_identity(path) != identity
    ):
        raise ValueError("external_skill_parent_changed")


def _is_reparse(node_stat: os.stat_result) -> bool:
    return bool(
        getattr(node_stat, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("external_skill_short_write")
        offset += written


def _no_fault(_stage: str) -> None:
    return None


__all__ = (
    "BUNDLE_FILE_PATHS",
    "BUNDLE_RESOURCE_NAME",
    "BundleValidationError",
    "compute_bundle_aggregate",
    "decode_skill_bundle",
    "external_skill_tree_identity",
    "install_external_skill",
    "load_embedded_skill_bundle",
)
