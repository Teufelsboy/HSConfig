"""Strict point-in-time resolution of one published configure output."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from hsconfig.atomic_io import ExclusiveFileLock
from hsconfig.package_io import (
    BoundedFilesystemPackageView,
    capture_plain_ancestor_guard,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_plain_directory,
    require_same_identity_resolution,
    snapshot_bounded_filesystem_package,
)
from hsconfig.run_manifest import MAX_MANIFEST_BYTES, TreeManifest
from hsconfig.strict_package_validation import (
    strict_validation_passed,
    validate_complete_package_from_view,
)
from hsconfig.strict_run_validation import verify_configure_run_package


CURRENT_PATH = "current.json"
CURRENT_SCHEMA_VERSION = 1
MAX_OUTPUT_ROOT_ENTRIES = 100
_CURRENT_KEYS = frozenset(
    {
        "schema_version",
        "deck_name",
        "deck_fingerprint",
        "revision",
        "content_root_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class OutputPublication:
    schema_version: int
    deck_name: str
    deck_fingerprint: str
    revision: str
    content_root_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != CURRENT_SCHEMA_VERSION
            or not isinstance(self.deck_name, str)
            or not self.deck_name
            or self.deck_name != self.deck_name.strip()
            or not _is_sha256(self.deck_fingerprint)
            or not _is_sha256(self.content_root_sha256)
            or self.revision
            != f"revisions/sha256-{self.content_root_sha256}"
        ):
            raise ValueError("output_publication_invalid")


@dataclass(frozen=True, slots=True)
class VerifiedRevision:
    manifest: TreeManifest
    snapshot: BoundedFilesystemPackageView


@dataclass(frozen=True, slots=True)
class PackageInputLease:
    package_root: Path
    publication: OutputPublication | None
    content_root_sha256: str | None
    output_root: Path | None
    snapshot: BoundedFilesystemPackageView | None


@contextmanager
def lease_package_input(package_input: Path) -> Iterator[PackageInputLease]:
    """Lease a published output root or preserve direct-package compatibility.

    Any publication-layout marker forces strict current-output resolution.
    The publish lock remains held for the complete lifetime of a published
    lease so a consumer can validate and read the selected revision safely.
    """

    candidate = Path(package_input)
    if not _has_output_layout_marker(candidate):
        yield PackageInputLease(
            package_root=candidate,
            publication=None,
            content_root_sha256=None,
            output_root=None,
            snapshot=None,
        )
        return

    try:
        guard = capture_plain_ancestor_guard(candidate / ".publish.lock")
        require_plain_directory(candidate)
        lock_path = candidate / ".publish.lock"
        if not path_lexists(lock_path):
            raise ValueError("current_output_invalid")
        plain_file_status(lock_path)
    except Exception as error:
        raise ValueError("current_output_invalid") from error

    with ExclusiveFileLock(lock_path):
        try:
            guard.validate()
            publication, verified = resolve_current_publication_unlocked(
                candidate
            )
            guard.validate()
        except Exception as error:
            raise ValueError("current_output_invalid") from error
        consumer_error: BaseException | None = None
        try:
            yield PackageInputLease(
                package_root=(
                    candidate / publication.revision / "04_package"
                ),
                publication=publication,
                content_root_sha256=publication.content_root_sha256,
                output_root=candidate,
                snapshot=verified.snapshot,
            )
        except BaseException as error:
            consumer_error = error
            raise
        finally:
            try:
                guard.validate()
            except Exception as error:
                if consumer_error is None:
                    raise
                consumer_error.add_note(
                    f"lease exit guard validation failed: {error}"
                )


def resolve_current_package(output_root: Path) -> Path:
    """Return the package selected and verified while holding the publish lock.

    The returned path is a point-in-time result. Callers that need continued
    lifetime guarantees must retain a snapshot or hold their own transaction;
    a later publisher may retire the revision after this function returns.
    """

    with lease_package_input(Path(output_root)) as lease:
        if lease.publication is None:
            raise ValueError("current_output_invalid")
        return lease.package_root


def resolve_current_publication_unlocked(
    output_root: Path,
) -> tuple[OutputPublication, VerifiedRevision]:
    """Resolve current under the caller-held publish lock."""

    try:
        require_plain_directory(output_root)
        _reject_current_aliases(output_root)
        pointer_path = output_root / CURRENT_PATH
        pointer_status = plain_file_status(pointer_path)
        pointer_bytes = read_file_no_follow(
            pointer_path,
            expected_status=pointer_status,
            maximum_size=MAX_MANIFEST_BYTES,
        )
        publication = parse_output_publication(pointer_bytes)
        revision_parent = output_root / "revisions"
        require_plain_directory(revision_parent)
        revision_root = revision_parent / Path(publication.revision).name
        require_plain_directory(revision_root)
        require_same_identity_resolution(revision_parent)
        require_same_identity_resolution(revision_root)
        verified = snapshot_and_verify_revision(revision_root)
        manifest = verified.manifest
        if (
            manifest.deck_name != publication.deck_name
            or manifest.deck_fingerprint != publication.deck_fingerprint
            or manifest.content_root_sha256
            != publication.content_root_sha256
        ):
            raise ValueError("current_identity_mismatch")
        return publication, verified
    except Exception as error:
        raise ValueError("current_output_invalid") from error


def snapshot_and_verify_revision(revision_root: Path) -> VerifiedRevision:
    snapshot = snapshot_bounded_filesystem_package(revision_root)
    _verify_exact_directory_set(snapshot)
    manifest, package = verify_configure_run_package(snapshot)
    report = validate_complete_package_from_view(package)
    if not strict_validation_passed(report):
        raise ValueError("published_package_semantics_invalid")
    return VerifiedRevision(manifest=manifest, snapshot=snapshot)


def parse_output_publication(content: bytes) -> OutputPublication:
    payload = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=_unique_json_object,
    )
    if not isinstance(payload, dict) or set(payload) != _CURRENT_KEYS:
        raise ValueError("output_publication_schema_invalid")
    publication = OutputPublication(
        schema_version=payload["schema_version"],
        deck_name=payload["deck_name"],
        deck_fingerprint=payload["deck_fingerprint"],
        revision=payload["revision"],
        content_root_sha256=payload["content_root_sha256"],
    )
    if content != output_publication_bytes(publication):
        raise ValueError("output_publication_noncanonical")
    return publication


def output_publication_bytes(publication: OutputPublication) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": publication.schema_version,
                "deck_name": publication.deck_name,
                "deck_fingerprint": publication.deck_fingerprint,
                "revision": publication.revision,
                "content_root_sha256": publication.content_root_sha256,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _verify_exact_directory_set(
    snapshot: BoundedFilesystemPackageView,
) -> None:
    expected: set[str] = set()
    for name in snapshot.file_names():
        parts = name.split("/")
        expected.update(
            "/".join(parts[:index])
            for index in range(1, len(parts))
        )
    if snapshot.directory_names != tuple(sorted(expected)):
        raise ValueError("published_tree_directory_set_invalid")


def _reject_current_aliases(output_root: Path) -> None:
    aliases: list[str] = []
    count = 0
    with os.scandir(output_root) as iterator:
        for entry in iterator:
            count += 1
            if count > MAX_OUTPUT_ROOT_ENTRIES:
                raise ValueError("output_root_entry_limit")
            if entry.name.casefold() == CURRENT_PATH.casefold():
                aliases.append(entry.name)
    if aliases != [CURRENT_PATH]:
        raise ValueError("current_output_claim_invalid")


def _has_output_layout_marker(candidate: Path) -> bool:
    if not path_lexists(candidate):
        return False
    try:
        require_plain_directory(candidate)
    except Exception as error:
        raise ValueError("current_output_invalid") from error
    count = 0
    try:
        with os.scandir(candidate) as iterator:
            for entry in iterator:
                count += 1
                if count > MAX_OUTPUT_ROOT_ENTRIES:
                    raise ValueError("output_root_entry_limit")
                if entry.name.casefold() in {
                    CURRENT_PATH.casefold(),
                    ".publish.lock",
                    ".publisher",
                    "revisions",
                }:
                    return True
    except OSError as error:
        raise ValueError("current_output_invalid") from error
    return False


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
    "OutputPublication",
    "PackageInputLease",
    "VerifiedRevision",
    "lease_package_input",
    "output_publication_bytes",
    "parse_output_publication",
    "resolve_current_package",
    "resolve_current_publication_unlocked",
    "snapshot_and_verify_revision",
)
