"""Canonical read-only inventory for audited HSConfig output roots."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from hsconfig.audited_deck_catalog import load_audited_deck_catalog
from hsconfig.build_input_catalog import load_packaged_audited_build_inputs
from hsconfig.current_output import (
    lease_package_input,
    snapshot_and_verify_revision,
)
from hsconfig.output_publisher import validate_finalized_publication_authority
from hsconfig.package_io import path_identity, path_identity_from_status


REVISION_NAME_RE = re.compile(r"sha256-[0-9a-f]{64}\Z")
_STAGING_RE = re.compile(r"\.staging-[0-9a-f]{32}\Z")
_TEMP_RE = re.compile(r"(?:^|[._-])(?:tmp|temp|temporary)(?:$|[._-])", re.I)
_BACKUP_RE = re.compile(r"(?:backup|\.bak$)", re.I)
_ROLLBACK_RE = re.compile(r"rollback", re.I)
_RECEIPT_RE = re.compile(
    r"(?:(?:orphan|runtime[_-]?apply|fake[_-]?apply|apply[_-]?history).*receipt|"
    r"receipt.*(?:orphan|runtime[_-]?apply|fake[_-]?apply|apply[_-]?history))",
    re.I,
)
CANONICAL_DECK_LAYOUT = frozenset(
    {".publish.lock", ".publisher", "current.json", "revisions"}
)
_COORDINATOR_PREFIX = ".hsconfig-output-reconcile-"
_ACTIVE_COORDINATOR_NAME = _COORDINATOR_PREFIX + "transaction"
_PREPARE_COORDINATOR_RE = re.compile(
    re.escape(_COORDINATOR_PREFIX) + r"prepare-[0-9a-f]{32}\Z"
)
_CLEANUP_COORDINATOR_RE = re.compile(
    re.escape(_COORDINATOR_PREFIX) + r"cleanup-[0-9a-f]{32}\Z"
)


@dataclass(frozen=True, slots=True)
class OutputInventory:
    audited_decks: int
    current_outputs: int
    revision_count: int
    staging_count: int
    unreferenced_revision_count: int
    backup_count: int
    rollback_count: int
    orphan_transaction_count: int
    orphan_receipt_count: int
    temporary_file_count: int
    invalid_count: int


@dataclass(frozen=True, slots=True)
class CatalogAuthority:
    catalog_path: Path
    names: tuple[str, ...]
    fingerprints: dict[str, str]


@dataclass(frozen=True, slots=True)
class ScanContext:
    """Identity and coordinator scope for one canonical scanner invocation."""

    expected_root_identity: tuple[int, int, int] | None = None
    include_sibling_coordinators: bool = True
    fail_on_identity_mismatch: bool = False

    @classmethod
    def identity_bound_staging(
        cls,
        identity: tuple[int, int, int],
    ) -> ScanContext:
        return cls(
            expected_root_identity=identity,
            include_sibling_coordinators=False,
            fail_on_identity_mismatch=True,
        )


def reconcile_audited_outputs(
    *,
    outputs_root: Path,
    catalog_path: Path,
) -> OutputInventory:
    """Return one deterministic public inventory, including coordinators."""

    return scan_inventory(
        Path(outputs_root),
        load_catalog_authority(catalog_path),
        context=ScanContext(),
    )


def load_catalog_authority(catalog_path: Path) -> CatalogAuthority:
    rows = tuple(load_audited_deck_catalog(catalog_path))
    audited = load_packaged_audited_build_inputs()
    if len(rows) != 12 or len(audited.builds) != 12:
        raise ValueError("reconcile_catalog_count_invalid")
    by_name = {build.deck_name: build for build in audited.builds}
    names = tuple(str(row["deck_name"]) for row in rows)
    if len(set(names)) != 12 or set(names) != set(by_name):
        raise ValueError("reconcile_catalog_deck_set_invalid")
    for row in rows:
        build = by_name[str(row["deck_name"])]
        digest = sha256(str(row["deck_code"]).encode("utf-8")).hexdigest()
        if digest != build.deck_code_sha256:
            raise ValueError("reconcile_catalog_identity_mismatch")
    return CatalogAuthority(
        catalog_path=Path(catalog_path),
        names=names,
        fingerprints={name: by_name[name].deck_fingerprint for name in names},
    )


def scan_inventory(
    outputs_root: Path,
    authority: CatalogAuthority,
    *,
    context: ScanContext,
) -> OutputInventory:
    counters = {
        "current_outputs": 0,
        "revision_count": 0,
        "staging_count": 0,
        "unreferenced_revision_count": 0,
        "backup_count": 0,
        "rollback_count": 0,
        "orphan_transaction_count": 0,
        "orphan_receipt_count": 0,
        "temporary_file_count": 0,
        "invalid_count": 0,
    }
    root = Path(os.path.abspath(outputs_root))
    if context.include_sibling_coordinators:
        _classify_sibling_coordinators(root.parent, counters)
    if not os.path.lexists(root):
        counters["invalid_count"] += len(authority.names)
        return OutputInventory(audited_decks=len(authority.names), **counters)
    if context.expected_root_identity is not None:
        try:
            identity_matches = (
                path_identity(root) == context.expected_root_identity
            )
        except (OSError, ValueError):
            identity_matches = False
        if not identity_matches:
            if context.fail_on_identity_mismatch:
                raise ValueError("reconcile_scan_root_identity_changed")
            counters["invalid_count"] += 1
    try:
        require_plain_directory(root)
        entries = plain_scandir(root)
    except ValueError:
        counters["invalid_count"] += len(authority.names) + 1
        return OutputInventory(audited_decks=len(authority.names), **counters)

    _classify_residue_tree(root, counters)
    entry_by_name = {entry.name: entry for entry in entries}
    if len({entry.name.casefold() for entry in entries}) != len(entries):
        counters["invalid_count"] += 1
    expected = set(authority.names)
    counters["invalid_count"] += sum(entry.name not in expected for entry in entries)

    for deck_name in authority.names:
        entry = entry_by_name.get(deck_name)
        if entry is None:
            counters["invalid_count"] += 1
            continue
        deck_root = root / deck_name
        try:
            require_plain_directory(deck_root)
            names = {child.name for child in plain_scandir(deck_root)}
        except ValueError:
            counters["invalid_count"] += 1
            continue
        unexpected = names - CANONICAL_DECK_LAYOUT
        if unexpected:
            counters["invalid_count"] += len(unexpected)

        revision_names: list[str] = []
        invalid_revisions = 0
        revisions_root = deck_root / "revisions"
        if os.path.lexists(revisions_root):
            try:
                require_plain_directory(revisions_root)
                for revision in plain_scandir(revisions_root):
                    if _STAGING_RE.fullmatch(revision.name):
                        counters["staging_count"] += 1
                    elif REVISION_NAME_RE.fullmatch(revision.name):
                        counters["revision_count"] += 1
                        revision_names.append(revision.name)
                    else:
                        counters["invalid_count"] += 1
            except ValueError:
                counters["invalid_count"] += 1

        referenced: str | None = None
        publication = None
        try:
            with lease_package_input(deck_root) as lease:
                publication = lease.publication
                if (
                    publication is None
                    or publication.deck_name != deck_name
                    or publication.deck_fingerprint != authority.fingerprints[deck_name]
                    or lease.content_root_sha256 != publication.content_root_sha256
                ):
                    raise ValueError("reconcile_current_identity_invalid")
                referenced = Path(publication.revision).name
                counters["current_outputs"] += 1
        except (OSError, ValueError):
            counters["invalid_count"] += 1
        for revision_name in revision_names:
            if publication is not None and revision_name == referenced:
                continue
            try:
                verified_revision = snapshot_and_verify_revision(
                    revisions_root / revision_name
                )
                if (
                    revision_name
                    != "sha256-" + verified_revision.manifest.content_root_sha256
                    or verified_revision.manifest.deck_name != deck_name
                    or verified_revision.manifest.deck_fingerprint
                    != authority.fingerprints[deck_name]
                ):
                    raise ValueError("reconcile_revision_identity_invalid")
            except (OSError, ValueError):
                invalid_revisions += 1
        counters["invalid_count"] += invalid_revisions
        if publication is not None:
            try:
                validate_finalized_publication_authority(deck_root, publication)
            except (OSError, ValueError):
                transaction_count = _publisher_transaction_file_count(deck_root)
                counters["orphan_transaction_count"] += max(
                    1,
                    transaction_count - 1,
                )
                counters["invalid_count"] += 1
        else:
            transactions = deck_root / ".publisher" / "transactions"
            if os.path.lexists(transactions):
                counters["orphan_transaction_count"] += max(
                    1,
                    _publisher_transaction_file_count(deck_root),
                )
        counters["unreferenced_revision_count"] += sum(
            name != referenced for name in revision_names
        )

    return OutputInventory(audited_decks=len(authority.names), **counters)


def _classify_sibling_coordinators(
    parent: Path,
    counters: dict[str, int],
) -> None:
    try:
        entries = plain_scandir(parent)
    except ValueError:
        counters["invalid_count"] += 1
        return
    for entry in entries:
        name = entry.name
        if not name.startswith(_COORDINATOR_PREFIX):
            continue
        recognized = (
            name == _ACTIVE_COORDINATOR_NAME
            or _PREPARE_COORDINATOR_RE.fullmatch(name) is not None
            or _CLEANUP_COORDINATOR_RE.fullmatch(name) is not None
        )
        counters["orphan_transaction_count"] += 1
        counters["invalid_count"] += 1
        if not recognized:
            counters["invalid_count"] += 1


def _classify_residue_tree(root: Path, counters: dict[str, int]) -> None:
    pending = [root]
    seen: set[tuple[int, int, int]] = set()
    while pending:
        directory = pending.pop()
        try:
            directory_stat = os.lstat(directory)
        except OSError:
            counters["invalid_count"] += 1
            continue
        identity = path_identity_from_status(directory_stat)
        if identity in seen:
            counters["invalid_count"] += 1
            continue
        seen.add(identity)
        try:
            entries = plain_scandir(directory)
        except ValueError:
            counters["invalid_count"] += 1
            continue
        for entry in entries:
            name = entry.name
            path = directory / name
            if _BACKUP_RE.search(name):
                counters["backup_count"] += 1
            if _ROLLBACK_RE.search(name):
                counters["rollback_count"] += 1
            if _TEMP_RE.search(name):
                counters["temporary_file_count"] += 1
            if _RECEIPT_RE.search(name) and entry.is_file(follow_symlinks=False):
                counters["orphan_receipt_count"] += 1
            try:
                node_stat = os.lstat(path)
            except OSError:
                counters["invalid_count"] += 1
                continue
            if status_is_reparse(node_stat):
                counters["invalid_count"] += 1
            elif stat.S_ISDIR(node_stat.st_mode):
                pending.append(path)
            elif stat.S_ISREG(node_stat.st_mode):
                if node_stat.st_nlink != 1:
                    counters["invalid_count"] += 1
            else:
                counters["invalid_count"] += 1


def _publisher_transaction_file_count(deck_root: Path) -> int:
    directory = deck_root / ".publisher" / "transactions"
    try:
        return sum(
            entry.is_file(follow_symlinks=False)
            for entry in plain_scandir(directory)
        )
    except ValueError:
        return 1


def plain_scandir(path: Path) -> tuple[os.DirEntry[str], ...]:
    require_plain_directory(path)
    try:
        with os.scandir(path) as iterator:
            return tuple(sorted(iterator, key=lambda entry: entry.name))
    except OSError as error:
        raise ValueError("reconcile_directory_scan_failed") from error


def require_plain_directory(path: Path) -> None:
    try:
        node_stat = os.lstat(path)
    except OSError as error:
        raise ValueError("reconcile_directory_invalid") from error
    if not stat.S_ISDIR(node_stat.st_mode) or status_is_reparse(node_stat):
        raise ValueError("reconcile_directory_invalid")


def status_is_reparse(node_stat: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    attributes = getattr(node_stat, "st_file_attributes", 0)
    return stat.S_ISLNK(node_stat.st_mode) or bool(attributes & reparse_flag)


def inventory_is_current(inventory: OutputInventory) -> bool:
    return inventory == OutputInventory(
        audited_decks=12,
        current_outputs=12,
        revision_count=12,
        staging_count=0,
        unreferenced_revision_count=0,
        backup_count=0,
        rollback_count=0,
        orphan_transaction_count=0,
        orphan_receipt_count=0,
        temporary_file_count=0,
        invalid_count=0,
    )


def inventory_json(inventory: OutputInventory) -> str:
    return json.dumps(asdict(inventory), ensure_ascii=False, indent=2) + "\n"


def inventory_text(inventory: OutputInventory) -> str:
    return "\n".join(
        f"{name}: {value}" for name, value in asdict(inventory).items()
    ) + "\n"
