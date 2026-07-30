"""Controlled publication of an already verified in-memory package."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath

from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import load_operator_summary_inputs
from hsconfig.package_derivation_receipt import (
    verify_package_derivation_receipt_from_view,
)
from hsconfig.package_model import (
    DirectoryPackageView,
    content_root_sha256,
)
from hsconfig.package_render_authority import (
    AuthorityArtifact,
    RenderedAuthorityPackage,
    render_package_authority,
)
from hsconfig.strict_package_validation import (
    validate_complete_package_from_view,
)


class PublicationFaultPoint(StrEnum):
    STAGING_CREATED = "staging_created"
    ARTIFACTS_WRITTEN = "artifacts_written"
    RELOADED = "reloaded"
    VERIFIED = "verified"
    BEFORE_COMMIT = "before_commit"
    AFTER_COMMIT = "after_commit"


PublicationFaultHook = Callable[[PublicationFaultPoint, Path], None]
_DirectoryIdentity = tuple[int, int]
_DestinationIdentity = tuple[int, int, int]
_ParentChain = tuple[tuple[Path, _DirectoryIdentity], ...]
_FileIdentities = dict[str, _DirectoryIdentity]
_DirectoryIdentities = dict[str, _DirectoryIdentity]


@dataclass(frozen=True, slots=True)
class PublishedPackage:
    destination: Path
    content_root_sha256: str


def publish_rendered_package(
    rendered: RenderedAuthorityPackage,
    destination: Path,
    *,
    fault_hook: PublicationFaultHook | None = None,
) -> PublishedPackage:
    """Publish exact bytes atomically, verify them, and roll back on failure."""

    if not isinstance(rendered, RenderedAuthorityPackage):
        raise TypeError("rendered_authority_package_required")
    if render_package_authority(rendered.model) != rendered:
        raise ValueError("rendered_authority_package_invalid")
    destination = Path(destination)
    if not destination.name:
        raise ValueError("publication_destination_invalid")
    _validate_parent_chain(destination.parent)
    destination_identity = _validate_destination(destination)
    existed_empty = destination_identity is not None
    created_parents: tuple[Path, ...] = ()
    staging: Path | None = None
    staging_identity: _DirectoryIdentity | None = None
    parent_chain: _ParentChain = ()
    file_identities: _FileIdentities = {}
    directory_identities: _DirectoryIdentities = {}
    published = False
    removed_empty_destination = False
    try:
        created_parents = _ensure_parent(destination.parent)
        parent_chain = _capture_parent_chain(destination.parent)
        _require_destination_identity(
            destination,
            destination_identity,
        )
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.staging-",
                dir=destination.parent,
            )
        )
        _require_parent_chain(parent_chain)
        staging_identity = _directory_identity(staging)
        _observe(
            fault_hook,
            PublicationFaultPoint.STAGING_CREATED,
            staging,
        )
        _require_parent_chain(parent_chain)
        _require_destination_identity(
            destination,
            destination_identity,
        )
        _require_directory_identity(staging, staging_identity)
        _write_exact_artifacts(
            rendered,
            staging,
            root_identity=staging_identity,
            parent_chain=parent_chain,
            file_identities=file_identities,
            directory_identities=directory_identities,
        )
        _observe(
            fault_hook,
            PublicationFaultPoint.ARTIFACTS_WRITTEN,
            staging,
        )
        _require_parent_chain(parent_chain)
        _require_destination_identity(
            destination,
            destination_identity,
        )
        _require_directory_identity(staging, staging_identity)

        view = DirectoryPackageView(staging)
        _observe(fault_hook, PublicationFaultPoint.RELOADED, staging)
        _require_parent_chain(parent_chain)
        _require_destination_identity(
            destination,
            destination_identity,
        )
        _verify_reloaded_package(
            rendered,
            view,
            root_identity=staging_identity,
            file_identities=file_identities,
            directory_identities=directory_identities,
        )
        _observe(fault_hook, PublicationFaultPoint.VERIFIED, staging)
        _require_parent_chain(parent_chain)
        _require_destination_identity(
            destination,
            destination_identity,
        )
        _require_directory_identity(staging, staging_identity)
        _observe(
            fault_hook,
            PublicationFaultPoint.BEFORE_COMMIT,
            staging,
        )
        _require_parent_chain(parent_chain)
        _require_destination_identity(
            destination,
            destination_identity,
        )
        _verify_reloaded_package(
            rendered,
            view,
            root_identity=staging_identity,
            file_identities=file_identities,
            directory_identities=directory_identities,
        )

        _require_parent_chain(parent_chain)
        if existed_empty:
            _require_destination_identity(
                destination,
                destination_identity,
            )
            destination.rmdir()
            removed_empty_destination = True
        staging.replace(destination)
        published = True
        _require_parent_chain(parent_chain)
        _require_directory_identity(destination, staging_identity)
        _observe(
            fault_hook,
            PublicationFaultPoint.AFTER_COMMIT,
            destination,
        )
        _require_parent_chain(parent_chain)
        _verify_reloaded_package(
            rendered,
            DirectoryPackageView(destination),
            root_identity=staging_identity,
            file_identities=file_identities,
            directory_identities=directory_identities,
        )
        return PublishedPackage(
            destination=destination,
            content_root_sha256=rendered.content_root_sha256,
        )
    except BaseException:
        _rollback(
            rendered=rendered,
            staging=staging,
            destination=destination,
            published=published,
            restore_empty_destination=removed_empty_destination,
            created_parents=created_parents,
            root_identity=staging_identity,
            parent_chain=parent_chain,
            file_identities=file_identities,
            directory_identities=directory_identities,
        )
        raise


def _validate_destination(
    destination: Path,
) -> _DestinationIdentity | None:
    try:
        stat_result = destination.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError("destination_must_be_empty") from error
    if (
        not stat.S_ISDIR(stat_result.st_mode)
        or _stat_is_reparse(stat_result)
    ):
        raise ValueError("destination_must_be_empty")
    try:
        if any(destination.iterdir()):
            raise ValueError("destination_must_be_empty")
    except OSError as error:
        raise ValueError("destination_must_be_empty") from error
    return _destination_identity(stat_result)


def _require_destination_identity(
    destination: Path,
    expected: _DestinationIdentity | None,
) -> None:
    if expected is None:
        try:
            destination.lstat()
        except FileNotFoundError:
            return
        except OSError as error:
            raise ValueError(
                "publication_destination_identity_mismatch"
            ) from error
        raise ValueError("publication_destination_identity_mismatch")
    try:
        stat_result = destination.lstat()
        empty = not any(destination.iterdir())
    except OSError as error:
        raise ValueError(
            "publication_destination_identity_mismatch"
        ) from error
    if (
        not stat.S_ISDIR(stat_result.st_mode)
        or _stat_is_reparse(stat_result)
        or _destination_identity(stat_result) != expected
        or not empty
    ):
        raise ValueError("publication_destination_identity_mismatch")


def _destination_identity(
    stat_result: os.stat_result,
) -> _DestinationIdentity:
    return (
        int(stat_result.st_dev),
        int(stat_result.st_ino),
        int(stat.S_IFMT(stat_result.st_mode)),
    )


def _validate_parent_chain(parent: Path) -> None:
    for ancestor in (parent, *parent.parents):
        try:
            stat_result = ancestor.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError("publication_parent_invalid") from error
        if (
            not stat.S_ISDIR(stat_result.st_mode)
            or _stat_is_reparse(stat_result)
        ):
            raise ValueError("publication_parent_invalid")


def _capture_parent_chain(parent: Path) -> _ParentChain:
    rows: list[tuple[Path, _DirectoryIdentity]] = []
    for ancestor in (parent, *parent.parents):
        try:
            rows.append((ancestor, _directory_identity(ancestor)))
        except ValueError as error:
            raise ValueError("publication_parent_invalid") from error
    return tuple(rows)


def _require_parent_chain(chain: _ParentChain) -> None:
    if not _parent_chain_matches(chain):
        raise ValueError("published_package_parent_identity_mismatch")


def _parent_chain_matches(chain: _ParentChain) -> bool:
    return bool(chain) and not any(
        not _directory_identity_matches(path, identity)
        for path, identity in chain
    )


def _ensure_parent(parent: Path) -> tuple[Path, ...]:
    missing: list[Path] = []
    cursor = parent
    while not cursor.exists():
        missing.append(cursor)
        next_cursor = cursor.parent
        if next_cursor == cursor:
            raise ValueError("publication_parent_invalid")
        cursor = next_cursor
    if not cursor.is_dir():
        raise ValueError("publication_parent_invalid")
    created = tuple(missing)
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except BaseException:
        _remove_created_parents(created)
        raise
    return created


def _write_exact_artifacts(
    rendered: RenderedAuthorityPackage,
    staging: Path,
    *,
    root_identity: _DirectoryIdentity,
    parent_chain: _ParentChain,
    file_identities: _FileIdentities,
    directory_identities: _DirectoryIdentities,
) -> None:
    for relative_path in _planned_directories(rendered):
        _require_parent_chain(parent_chain)
        _require_directory_identity(staging, root_identity)
        parent = PurePosixPath(relative_path).parent
        _require_owned_directory(
            staging,
            parent,
            root_identity=root_identity,
            directory_identities=directory_identities,
        )
        target = staging / relative_path
        try:
            target.lstat()
        except FileNotFoundError:
            pass
        else:
            raise ValueError("published_package_tree_shape_mismatch")
        try:
            target.mkdir()
        except OSError as error:
            raise ValueError(
                "published_package_tree_shape_mismatch"
            ) from error
        directory_identities[relative_path] = _directory_identity(target)

    for artifact in rendered.artifacts.artifacts:
        _require_parent_chain(parent_chain)
        _require_directory_identity(staging, root_identity)
        _require_owned_directory(
            staging,
            PurePosixPath(artifact.relative_path).parent,
            root_identity=root_identity,
            directory_identities=directory_identities,
        )
        target = staging / artifact.relative_path
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_BINARY", 0)
        )
        try:
            descriptor = os.open(target, flags, 0o600)
        except OSError as error:
            raise ValueError(
                "published_package_tree_shape_mismatch"
            ) from error
        try:
            remaining = memoryview(artifact.content)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    raise OSError("publication_write_incomplete")
                remaining = remaining[written:]
            os.fsync(descriptor)
            written_stat = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        current_stat = target.lstat()
        if (
            not stat.S_ISREG(written_stat.st_mode)
            or _stat_is_reparse(written_stat)
            or _node_identity(written_stat)
            != _node_identity(current_stat)
            or current_stat.st_size != artifact.size
        ):
            raise ValueError("published_package_artifact_identity_mismatch")
        file_identities[artifact.relative_path] = _node_identity(
            current_stat
        )


def _planned_directories(
    rendered: RenderedAuthorityPackage,
) -> tuple[str, ...]:
    directories: set[str] = set()
    for relative_path in rendered.artifacts.file_names():
        parent = PurePosixPath(relative_path).parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return tuple(
        sorted(
            directories,
            key=lambda value: (
                len(PurePosixPath(value).parts),
                value,
            ),
        )
    )


def _require_owned_directory(
    root: Path,
    relative_path: PurePosixPath,
    *,
    root_identity: _DirectoryIdentity,
    directory_identities: _DirectoryIdentities,
) -> None:
    if relative_path == PurePosixPath("."):
        _require_directory_identity(root, root_identity)
        return
    relative = relative_path.as_posix()
    expected = directory_identities.get(relative)
    if (
        expected is None
        or not _directory_identity_matches(root / relative, expected)
    ):
        raise ValueError("published_package_tree_shape_mismatch")


def _verify_reloaded_package(
    rendered: RenderedAuthorityPackage,
    view: DirectoryPackageView,
    *,
    root_identity: _DirectoryIdentity,
    file_identities: _FileIdentities,
    directory_identities: _DirectoryIdentities,
) -> None:
    _verify_owned_identities(
        rendered,
        view.root,
        root_identity=root_identity,
        file_identities=file_identities,
        directory_identities=directory_identities,
    )
    _verify_physical_tree_shape(
        rendered,
        view.root,
        root_identity=root_identity,
    )
    if view.file_names() != rendered.artifacts.file_names():
        raise ValueError("published_package_file_set_mismatch")
    reloaded: list[AuthorityArtifact] = []
    for expected in rendered.artifacts.artifacts:
        actual = AuthorityArtifact.from_content(
            relative_path=expected.relative_path,
            content=view.read_bytes(expected.relative_path),
        )
        if actual != expected:
            raise ValueError(
                "published_package_artifact_mismatch:"
                f"{expected.relative_path}"
            )
        reloaded.append(actual)
    if content_root_sha256(tuple(reloaded)) != rendered.content_root_sha256:
        raise ValueError("published_package_content_root_mismatch")

    validation = validate_complete_package_from_view(view)
    if validation != view.read_json("reports/validation_report.json"):
        raise ValueError("published_package_validation_replay_mismatch")
    receipt = view.read_json("package_derivation_receipt.json")
    verified, reasons = verify_package_derivation_receipt_from_view(
        view,
        receipt,
    )
    if not verified or reasons:
        raise ValueError("published_package_receipt_verification_failed")
    replay_inputs = load_operator_summary_inputs(view)
    if (
        replay_inputs.authority.package_summary_parity is not True
        or build_operator_summary_from_inputs(replay_inputs)
        != view.read_json("reports/operator_summary.json")
    ):
        raise ValueError(
            "published_package_operator_summary_replay_failed"
        )


def _verify_owned_identities(
    rendered: RenderedAuthorityPackage,
    root: Path,
    *,
    root_identity: _DirectoryIdentity,
    file_identities: _FileIdentities,
    directory_identities: _DirectoryIdentities,
) -> None:
    _require_directory_identity(root, root_identity)
    if set(directory_identities) != set(_planned_directories(rendered)):
        raise ValueError("published_package_artifact_identity_mismatch")
    for relative_path, identity in directory_identities.items():
        if not _directory_identity_matches(
            root / relative_path,
            identity,
        ):
            raise ValueError(
                "published_package_artifact_identity_mismatch"
            )
    if set(file_identities) != set(rendered.artifacts.file_names()):
        raise ValueError("published_package_artifact_identity_mismatch")
    for relative_path, identity in file_identities.items():
        target = root / relative_path
        try:
            stat_result = target.lstat()
        except OSError as error:
            raise ValueError(
                "published_package_artifact_identity_mismatch"
            ) from error
        if (
            not stat.S_ISREG(stat_result.st_mode)
            or _stat_is_reparse(stat_result)
            or _node_identity(stat_result) != identity
        ):
            raise ValueError(
                "published_package_artifact_identity_mismatch"
            )


def _rollback(
    *,
    rendered: RenderedAuthorityPackage,
    staging: Path | None,
    destination: Path,
    published: bool,
    restore_empty_destination: bool,
    created_parents: tuple[Path, ...],
    root_identity: _DirectoryIdentity | None,
    parent_chain: _ParentChain,
    file_identities: _FileIdentities,
    directory_identities: _DirectoryIdentities,
) -> None:
    if parent_chain and not _parent_chain_matches(parent_chain):
        return
    if published:
        _remove_published_artifacts(
            rendered,
            destination,
            root_identity=root_identity,
            file_identities=file_identities,
            directory_identities=directory_identities,
        )
    elif staging is not None and staging.exists():
        _remove_staging_tree(
            rendered,
            staging,
            parent=destination.parent,
            root_identity=root_identity,
            file_identities=file_identities,
            directory_identities=directory_identities,
        )
    if restore_empty_destination and not destination.exists():
        destination.mkdir(parents=False)
    if not restore_empty_destination:
        _remove_created_parents(created_parents)


def _remove_published_artifacts(
    rendered: RenderedAuthorityPackage,
    destination: Path,
    *,
    root_identity: _DirectoryIdentity | None,
    file_identities: _FileIdentities,
    directory_identities: _DirectoryIdentities,
) -> None:
    if (
        root_identity is None
        or not _directory_identity_matches(destination, root_identity)
    ):
        return
    actual_directories = _locate_owned_directories(
        destination,
        root_identity=root_identity,
        directory_identities=directory_identities,
    )
    for artifact in rendered.artifacts.artifacts:
        target = _verified_owned_regular_file(
            destination,
            artifact,
            root_identity=root_identity,
            expected_identity=file_identities.get(
                artifact.relative_path
            ),
            directory_identities=directory_identities,
            actual_directories=actual_directories,
        )
        if target is not None:
            target.unlink()
    _prune_owned_directories(
        destination,
        root_identity=root_identity,
        directory_identities=directory_identities,
        actual_directories=actual_directories,
    )
    _remove_safe_unbound_nodes_in_owned_directories(
        destination,
        root_identity=root_identity,
        directory_identities=directory_identities,
        actual_directories=actual_directories,
    )
    if (
        _directory_identity_matches(destination, root_identity)
        and not any(destination.iterdir())
    ):
        destination.rmdir()


def _verify_physical_tree_shape(
    rendered: RenderedAuthorityPackage,
    root: Path,
    *,
    root_identity: _DirectoryIdentity,
) -> None:
    _require_directory_identity(root, root_identity)
    expected_files = set(rendered.artifacts.file_names())
    expected_directories: set[str] = set()
    for relative_path in expected_files:
        parent = PurePosixPath(relative_path).parent
        while parent != PurePosixPath("."):
            expected_directories.add(parent.as_posix())
            parent = parent.parent
    actual_files, actual_directories = _physical_tree_shape(
        root,
        root_identity=root_identity,
    )
    if (
        actual_files != expected_files
        or actual_directories != expected_directories
    ):
        raise ValueError("published_package_tree_shape_mismatch")


def _locate_owned_directories(
    root: Path,
    *,
    root_identity: _DirectoryIdentity,
    directory_identities: _DirectoryIdentities,
) -> dict[str, Path]:
    if not _directory_identity_matches(root, root_identity):
        return {}
    located: dict[str, Path] = {}
    for relative_path, identity in sorted(
        directory_identities.items(),
        key=lambda value: (
            len(PurePosixPath(value[0]).parts),
            value[0],
        ),
    ):
        parent_relative = PurePosixPath(relative_path).parent
        parent = (
            root
            if parent_relative == PurePosixPath(".")
            else located.get(parent_relative.as_posix())
        )
        if parent is None or not _normal_directory_exists(parent):
            continue
        matches: list[Path] = []
        with os.scandir(parent) as entries:
            rows = list(entries)
        for entry in rows:
            path = Path(entry.path)
            stat_result = entry.stat(follow_symlinks=False)
            if (
                entry.is_symlink()
                or _stat_is_reparse(stat_result)
                or not entry.is_dir(follow_symlinks=False)
            ):
                continue
            if _directory_identity_matches(path, identity):
                matches.append(path)
        if len(matches) == 1:
            located[relative_path] = matches[0]
    return located


def _physical_tree_shape(
    root: Path,
    *,
    root_identity: _DirectoryIdentity,
) -> tuple[set[str], set[str]]:
    _require_directory_identity(root, root_identity)
    files: set[str] = set()
    directories: set[str] = set()
    stack = [root]
    while stack:
        directory = stack.pop()
        _require_normal_directory(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                path = Path(entry.path)
                relative_path = path.relative_to(root).as_posix()
                stat_result = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or (
                    getattr(stat_result, "st_file_attributes", 0)
                    & 0x400
                ):
                    raise ValueError(
                        "published_package_tree_shape_mismatch"
                    )
                if entry.is_file(follow_symlinks=False):
                    files.add(relative_path)
                elif entry.is_dir(follow_symlinks=False):
                    directories.add(relative_path)
                    stack.append(path)
                else:
                    raise ValueError(
                        "published_package_tree_shape_mismatch"
                    )
    return files, directories


def _prune_owned_directories(
    root: Path,
    *,
    root_identity: _DirectoryIdentity,
    directory_identities: _DirectoryIdentities,
    actual_directories: dict[str, Path],
) -> None:
    if not _directory_identity_matches(root, root_identity):
        return
    for relative_path, identity in sorted(
        directory_identities.items(),
        key=lambda value: len(PurePosixPath(value[0]).parts),
        reverse=True,
    ):
        directory = actual_directories.get(relative_path)
        if directory is None:
            continue
        if (
            _directory_identity_matches(directory, identity)
            and not any(directory.iterdir())
        ):
            directory.rmdir()


def _remove_safe_unbound_nodes_in_owned_directories(
    root: Path,
    *,
    root_identity: _DirectoryIdentity,
    directory_identities: _DirectoryIdentities,
    actual_directories: dict[str, Path],
) -> None:
    if not _directory_identity_matches(root, root_identity):
        return
    owned_parents = {
        ".": (root, root_identity),
        **{
            relative_path: (
                path,
                directory_identities[relative_path],
            )
            for relative_path, path in actual_directories.items()
        },
    }
    owned_directory_paths = set(actual_directories.values())
    for parent, identity in owned_parents.values():
        if not _directory_identity_matches(parent, identity):
            continue
        with os.scandir(parent) as entries:
            rows = list(entries)
        for entry in rows:
            path = Path(entry.path)
            if path in owned_directory_paths:
                continue
            stat_result = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or _stat_is_reparse(stat_result):
                _remove_reparse_node(path, stat_result)
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            try:
                directory_identity = _directory_identity(path)
                empty = not any(path.iterdir())
            except (OSError, ValueError):
                continue
            if empty and _directory_identity_matches(
                path,
                directory_identity,
            ):
                path.rmdir()


def _directory_identity(path: Path) -> _DirectoryIdentity:
    try:
        stat_result = path.lstat()
    except OSError as error:
        raise ValueError(
            "published_package_root_identity_mismatch"
        ) from error
    if (
        not stat.S_ISDIR(stat_result.st_mode)
        or _stat_is_reparse(stat_result)
    ):
        raise ValueError("published_package_root_identity_mismatch")
    return (int(stat_result.st_dev), int(stat_result.st_ino))


def _directory_identity_matches(
    path: Path,
    expected: _DirectoryIdentity,
) -> bool:
    try:
        return _directory_identity(path) == expected
    except ValueError:
        return False


def _require_directory_identity(
    path: Path,
    expected: _DirectoryIdentity,
) -> None:
    if not _directory_identity_matches(path, expected):
        raise ValueError("published_package_root_identity_mismatch")


def _require_normal_directory(path: Path) -> None:
    if not _normal_directory_exists(path):
        raise ValueError("published_package_tree_shape_mismatch")


def _normal_directory_exists(path: Path) -> bool:
    try:
        stat_result = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(stat_result.st_mode)
        and not _stat_is_reparse(stat_result)
    )


def _stat_is_reparse(stat_result: os.stat_result) -> bool:
    return bool(
        stat.S_ISLNK(stat_result.st_mode)
        or getattr(stat_result, "st_file_attributes", 0) & 0x400
    )


def _verified_owned_regular_file(
    root: Path,
    artifact: AuthorityArtifact,
    *,
    root_identity: _DirectoryIdentity,
    expected_identity: _DirectoryIdentity | None,
    directory_identities: _DirectoryIdentities,
    actual_directories: dict[str, Path],
) -> Path | None:
    if expected_identity is None:
        return None
    target = _actual_artifact_target(
        root,
        artifact.relative_path,
        root_identity=root_identity,
        directory_identities=directory_identities,
        actual_directories=actual_directories,
    )
    if target is None:
        return None
    try:
        before = target.lstat()
    except OSError:
        return None
    if (
        not stat.S_ISREG(before.st_mode)
        or _stat_is_reparse(before)
        or before.st_size != artifact.size
        or _node_identity(before) != expected_identity
    ):
        return None
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(target, flags)
    except OSError:
        return None
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _stat_is_reparse(opened)
            or _node_identity(opened) != _node_identity(before)
        ):
            return None
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
    finally:
        os.close(descriptor)
    if content != artifact.content:
        return None
    if _actual_artifact_target(
        root,
        artifact.relative_path,
        root_identity=root_identity,
        directory_identities=directory_identities,
        actual_directories=actual_directories,
    ) != target:
        return None
    try:
        current = target.lstat()
    except OSError:
        return None
    if (
        not stat.S_ISREG(current.st_mode)
        or _stat_is_reparse(current)
        or _node_identity(current) != _node_identity(before)
    ):
        return None
    return target


def _actual_artifact_target(
    root: Path,
    relative_path: str,
    *,
    root_identity: _DirectoryIdentity,
    directory_identities: _DirectoryIdentities,
    actual_directories: dict[str, Path],
) -> Path | None:
    if not _directory_identity_matches(root, root_identity):
        return None
    path = PurePosixPath(relative_path)
    parent_relative = path.parent
    if parent_relative == PurePosixPath("."):
        parent = root
    else:
        parent_key = parent_relative.as_posix()
        parent = actual_directories.get(parent_key)
        expected = directory_identities.get(parent_key)
        if (
            parent is None
            or expected is None
            or not _directory_identity_matches(parent, expected)
        ):
            return None
    return parent / path.name


def _node_identity(stat_result: os.stat_result) -> tuple[int, int]:
    return (int(stat_result.st_dev), int(stat_result.st_ino))


def _remove_created_parents(created_parents: tuple[Path, ...]) -> None:
    for parent in created_parents:
        if (
            _normal_directory_exists(parent)
            and not any(parent.iterdir())
        ):
            parent.rmdir()


def _remove_staging_tree(
    rendered: RenderedAuthorityPackage,
    path: Path,
    *,
    parent: Path,
    root_identity: _DirectoryIdentity | None,
    file_identities: _FileIdentities,
    directory_identities: _DirectoryIdentities,
) -> None:
    if path.parent.resolve() != parent.resolve():
        raise RuntimeError("publication_rollback_target_invalid")
    try:
        root_stat = path.lstat()
    except OSError:
        return
    if _stat_is_reparse(root_stat):
        _remove_reparse_node(path, root_stat)
        return
    if (
        root_identity is None
        or not _directory_identity_matches(path, root_identity)
    ):
        return
    _remove_published_artifacts(
        rendered,
        path,
        root_identity=root_identity,
        file_identities=file_identities,
        directory_identities=directory_identities,
    )


def _remove_reparse_node(
    path: Path,
    stat_result: os.stat_result,
) -> None:
    if stat.S_ISLNK(stat_result.st_mode):
        path.unlink()
    elif stat.S_ISDIR(stat_result.st_mode):
        path.rmdir()
    else:
        path.unlink()


def _observe(
    hook: PublicationFaultHook | None,
    point: PublicationFaultPoint,
    active: Path,
) -> None:
    if hook is not None:
        hook(point, active)


__all__ = (
    "PublicationFaultHook",
    "PublicationFaultPoint",
    "PublishedPackage",
    "publish_rendered_package",
)
