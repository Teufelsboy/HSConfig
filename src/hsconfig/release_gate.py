"""Canonical, fail-closed orchestration for the local release contract."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.parser import Parser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import threading
import time
import tomllib
from typing import Any, Literal
import unicodedata
import uuid
import zipfile

from packaging.tags import parse_tag
from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename
import hsconfig.publishable_tree as publishable_tree_module

from hsconfig.near100_scorecard import (
    ATOMIC_CHECK_OWNERS,
    HARD_METRIC_IDS,
    SEMANTIC_CARD_MODULE_COUNT,
    SEMANTIC_CLAIM_COUNT,
)
from hsconfig.publishable_tree import (
    EXACT_PLACEHOLDER_REFERENCE_SHA256,
    PublishableTreeError,
    SOURCE_TODO_ALLOWLIST,
    _ABSOLUTE_USER_PATH,
    _is_sensitive_credential_name as publishable_sensitive_credential_name,
    _shannon_entropy as publishable_shannon_entropy,
    contains_secret,
    evaluate_repository_tree,
    publishable_path_violations,
    publishable_text_violations,
)
from hsconfig.semantic_inventory import canonical_semantic_claim, validate_semantic_inventory
from hsconfig.version import __version__


TreeMode = Literal["working-pre-cutover", "candidate", "final"]

_EXACT_PLACEHOLDER_REFERENCE_SHA256 = EXACT_PLACEHOLDER_REFERENCE_SHA256

CHECK_NAMES = (
    "ruff",
    "full_tests_and_coverage",
    "contract_spine",
    "twelve_deck_acceptance",
    "contract_mutations",
    "dependency_audit",
    "distribution",
    "twelve_deck_determinism",
    "publishable_path_scan",
    "output_inventory",
    "package_immutability",
    "transaction_fault_matrix",
    "repository_hygiene",
    "version_consistency",
    "near100_scorecard",
)

_HISTORICAL_PREFIXES = (
    "docs/superpowers/plans/",
    "docs/research/",
    "docs/history/",
)
_LIVE_RESIDUE_DIRECTORY = re.compile(
    r"(?i)(?:__pycache__|\.cache|\.pytest_cache|\.ruff_cache|\.mypy_cache|\.hypothesis|"
    r"\.tox|\.nox|\.idea|\.vscode|\.codex-qa(?:[-_.][^/\\]+)?|[^/\\]+\.egg-info|build|dist|tmp|temp|"
    r"\.staging[^/\\]*|staging|backup|backups|"
    r"obsolete|old_generation)"
)
_LIVE_RESIDUE_FILE = re.compile(
    r"(?i)(?:\.coverage(?:\..+)?|coverage\.xml|\.DS_Store|[^/\\]+\.(?:pyc|pyo|swp|swo|tmp))$"
)
_GITHUB_CHECK_IDS = frozenset(
    check_id
    for check_id, owner in ATOMIC_CHECK_OWNERS.items()
    if owner == "github_repository_polish"
)
_MAX_ARCHIVE_MEMBERS = 10_000
_MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVE_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_ARCHIVE_COMPRESSION_RATIO = 200
_MAX_PUBLISHABLE_FILE_BYTES = 128 * 1024 * 1024
_GIT_BLOB_BATCH_LAUNCHER = (
    "import json,subprocess,sys; line=sys.stdin.buffer.readline(65537); "
    "(line.endswith(b'\\n') and len(line)<=65536) or sys.exit(2); "
    "argv=json.loads(line); "
    "(isinstance(argv,list) and 1<=len(argv)<=32 and "
    "all(isinstance(value,str) and value for value in argv)) or sys.exit(2); "
    "payload=sys.stdin.buffer.read(410001); len(payload)<=410000 or sys.exit(2); "
    "raise SystemExit(subprocess.run(argv,input=payload,shell=False).returncode)"
)
_MAX_ZIP_MEMBER_NAME_BYTES = 4 * 1024
_SUPPORTED_CORE_METADATA_VERSIONS = frozenset(
    {"1.0", "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "2.5"}
)
_FINAL_EVIDENCE_MAX_AGE_SECONDS = 300
_SEMANTIC_REPORT_CLAIM_OCCURRENCES = 426

class ReleaseGateError(ValueError):
    """Raised when the release gate cannot safely inspect its inputs."""


def _contains_secret(
    value: str,
    *,
    python_source: bool = False,
    structured_suffix: str = "",
) -> bool:
    return contains_secret(
        value,
        python_source=python_source,
        structured_suffix=structured_suffix,
    )


_is_sensitive_credential_name = publishable_sensitive_credential_name
_shannon_entropy = publishable_shannon_entropy


def _redact_text(value: str) -> str:
    if _contains_secret(value):
        return "[redacted-secret]"
    if _ABSOLUTE_USER_PATH.search(value):
        return "[redacted-local-path]"
    return value


def _portable_value(value: Any) -> Any:
    if isinstance(value, str):
        redacted = _redact_text(value)
        if redacted != value:
            return redacted
        if len(value) > 2_000:
            return {
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
                "redacted": "oversized-output",
            }
        return value
    if isinstance(value, Mapping):
        portable: dict[str, Any] = {}
        for key, item in value.items():
            original = str(key)
            sensitive_key = _contains_secret(original) or _is_sensitive_credential_name(
                original
            )
            redacted = "[redacted-sensitive-key]" if sensitive_key else _redact_text(original)
            if redacted != original:
                digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:12]
                safe_key = f"{redacted}:{digest}"
            else:
                safe_key = original
            portable[safe_key] = (
                "[redacted-secret]" if sensitive_key else _portable_value(item)
            )
        return portable
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_portable_value(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class _GateSnapshot:
    commit_oid: str
    tree_oid: str
    repository_fingerprint: str
    outputs_inventory_sha256: str
    repository_identity: str
    repository_path_identity: tuple[int, ...]
    outputs_path_identity: tuple[int, ...]
    owner_repository_snapshot: tuple[str, ...] | None
    owner_path_identity: tuple[int, ...] | None


@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    name: str
    passed: bool
    command: tuple[str, ...]
    details: Mapping[str, Any]

    def to_document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "command": [_portable_value(value) for value in self.command],
            "details": _portable_value(dict(self.details)),
        }


@dataclass(frozen=True, slots=True)
class ReleaseGateResult:
    passed: bool
    final_release_ready: bool
    version: str
    commit_oid: str
    checks: tuple[ReleaseCheck, ...]

    def to_document(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "final_release_ready": self.final_release_ready,
            "version": self.version,
            "commit_oid": self.commit_oid,
            "checks": [check.to_document() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_document(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class _CommandSpec:
    name: str
    command: tuple[str, ...]
    timeout: int


def _base_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        upper = key.upper()
        if upper.startswith("GIT_"):
            environment.pop(key, None)
    return environment


def _git_completed(
    repository: Path, *arguments: str, text: bool = True, check: bool = True
) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ("git", *arguments),
            cwd=repository,
            check=check,
            capture_output=True,
            text=text,
            shell=False,
            timeout=60,
            env=_base_environment(),
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReleaseGateError(f"repository inspection failed: {exc}") from exc


def _git(repository: Path, *arguments: str, text: bool = True) -> str | bytes:
    return _git_completed(repository, *arguments, text=text).stdout


def _resolve_git_path(repository: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = repository / path
    return path.resolve()


def _validate_git_binding(repository: Path) -> None:
    root = repository.resolve()
    top = Path(str(_git(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    git_dir = _resolve_git_path(
        root, str(_git(root, "rev-parse", "--absolute-git-dir")).strip()
    )
    common_dir = _resolve_git_path(
        root, str(_git(root, "rev-parse", "--git-common-dir")).strip()
    )
    inside = str(_git(root, "rev-parse", "--is-inside-work-tree")).strip()
    expected_git = (root / ".git").resolve()
    if top != root or inside != "true" or git_dir != expected_git or common_dir != expected_git:
        raise ReleaseGateError("Git repository/worktree binding does not match requested root")
    metadata = (root / ".git").lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
        raise ReleaseGateError("Git directory is not a private repository directory")
    worktree = _git_completed(root, "config", "--local", "--get", "core.worktree", check=False)
    if worktree.returncode not in {0, 1}:
        raise ReleaseGateError("Git core.worktree inspection failed")
    if worktree.returncode == 0:
        configured = _resolve_git_path(root / ".git", str(worktree.stdout).strip())
        if configured != root:
            raise ReleaseGateError("Git core.worktree does not match requested root")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise ReleaseGateError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def _load_json_bytes(data: bytes, *, source: str) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except ReleaseGateError:
        raise
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ReleaseGateError(f"invalid JSON evidence: {source}") from exc


def _is_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _process_tree_gate_interpreter(fallback: str | Path) -> str:
    if os.name != "nt":
        return str(fallback)
    raw_base = getattr(sys, "_base_executable", None)
    if not isinstance(raw_base, str) or not raw_base:
        raise ReleaseGateError("process gate interpreter is invalid")
    candidate = Path(raw_base)
    if not candidate.is_absolute():
        raise ReleaseGateError("process gate interpreter is invalid")
    try:
        metadata = candidate.lstat()
        canonical = candidate.resolve(strict=True)
        canonical_metadata = canonical.lstat()
    except (OSError, RuntimeError) as exc:
        raise ReleaseGateError("process gate interpreter is invalid") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(canonical_metadata.st_mode)
        or _is_reparse(canonical_metadata)
        or not stat.S_ISREG(canonical_metadata.st_mode)
    ):
        raise ReleaseGateError("process gate interpreter is invalid")
    return str(canonical)


def _walk_regular_tree(
    root: Path, *, context: str
) -> tuple[tuple[str, Path, os.stat_result], ...]:
    root_metadata = root.lstat()
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or _is_reparse(root_metadata)
    ):
        raise ReleaseGateError(f"{context} root is link/reparse/non-directory")
    rows: list[tuple[str, Path, os.stat_result]] = []

    def visit(directory: Path, prefix: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError as exc:
            raise ReleaseGateError(f"{context} directory is unreadable") from exc
        seen: dict[str, str] = {}
        for entry in entries:
            key = entry.name.casefold()
            previous = seen.get(key)
            if previous is not None and previous != entry.name:
                raise ReleaseGateError(f"{context} casefold collision: {previous}:{entry.name}")
            seen[key] = entry.name
            relative = prefix / entry.name
            path = Path(entry.path)
            metadata = path.lstat()
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode) and not _is_reparse(metadata):
                visit(path, relative)
            elif (
                stat.S_ISREG(metadata.st_mode)
                and not _is_reparse(metadata)
                and getattr(metadata, "st_nlink", 1) in {0, 1}
            ):
                rows.append((relative.as_posix(), path, metadata))
            else:
                raise ReleaseGateError(f"{context} contains link/hardlink/reparse/non-regular entry: {relative.as_posix()}")

    visit(root, PurePosixPath())
    return tuple(rows)


def _secure_regular_file(root: Path, relative: PurePosixPath) -> Path:
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleaseGateError(f"non-canonical evidence path: {relative.as_posix()}")
    try:
        root_stat = root.lstat()
    except OSError as exc:
        raise ReleaseGateError("evidence root cannot be inspected") from exc
    if not stat.S_ISDIR(root_stat.st_mode) or stat.S_ISLNK(root_stat.st_mode) or _is_reparse(root_stat):
        raise ReleaseGateError("evidence root must be a regular directory")
    candidate = root
    for index, part in enumerate(relative.parts):
        candidate = candidate / part
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise ReleaseGateError(f"evidence path is unavailable: {relative.as_posix()}") from exc
        final = index == len(relative.parts) - 1
        expected = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
        if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ReleaseGateError(f"evidence path contains link/reparse/non-regular data: {relative.as_posix()}")
        if final and getattr(metadata, "st_nlink", 1) not in {0, 1}:
            raise ReleaseGateError(f"evidence path must not be a hardlink: {relative.as_posix()}")
    return candidate


def _stat_identity(metadata: os.stat_result) -> tuple[Any, ...]:
    device = getattr(metadata, "st_dev", None)
    inode = getattr(metadata, "st_ino", None)
    if device is None or inode in {None, 0}:
        raise ReleaseGateError("filesystem identity is unavailable")
    return (
        stat.S_IFMT(metadata.st_mode),
        device,
        inode,
        getattr(metadata, "st_file_attributes", None),
        getattr(metadata, "st_reparse_tag", None),
    )


def _stat_content_signature(metadata: os.stat_result) -> tuple[Any, ...]:
    return (
        *_stat_identity(metadata),
        metadata.st_size,
        getattr(metadata, "st_mtime_ns", None),
        getattr(metadata, "st_ctime_ns", None),
        getattr(metadata, "st_nlink", 1),
    )


def _path_snapshots(
    root: Path,
    relative: PurePosixPath,
    *,
    context: str,
) -> tuple[tuple[Path, tuple[Any, ...]], ...]:
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReleaseGateError(f"{context} has a non-canonical path: {relative.as_posix()}")
    snapshots: list[tuple[Path, tuple[Any, ...]]] = []
    candidate = root
    components = (None, *relative.parts)
    for index, part in enumerate(components):
        if part is not None:
            candidate = candidate / part
        try:
            metadata = candidate.lstat()
        except OSError as exc:
            raise ReleaseGateError(f"{context} path cannot be inspected: {relative.as_posix()}") from exc
        final = index == len(components) - 1
        expected = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
        if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ReleaseGateError(
                f"{context} path contains link/reparse/non-regular data: {relative.as_posix()}"
            )
        if final and getattr(metadata, "st_nlink", 1) not in {0, 1}:
            raise ReleaseGateError(f"{context} path must not be a hardlink: {relative.as_posix()}")
        snapshots.append((candidate, _stat_identity(metadata)))
    return tuple(snapshots)


def _assert_path_snapshots(
    snapshots: tuple[tuple[Path, tuple[Any, ...]], ...],
    *,
    context: str,
) -> None:
    for path, expected in snapshots:
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise ReleaseGateError(f"{context} path changed during inspection") from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
            or _stat_identity(metadata) != expected
        ):
            raise ReleaseGateError(f"{context} path identity changed during inspection")


@contextmanager
def _secure_open_regular(
    root: Path,
    relative: PurePosixPath,
    *,
    context: str,
    max_bytes: int = _MAX_PUBLISHABLE_FILE_BYTES,
    expected_identity: tuple[Any, ...] | None = None,
) -> Any:
    snapshots = _path_snapshots(root, relative, context=context)
    candidate = snapshots[-1][0]
    validated_identity = snapshots[-1][1]
    if expected_identity is not None and validated_identity != expected_identity:
        raise ReleaseGateError(f"{context} path identity changed before inspection")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise ReleaseGateError(f"{context} path cannot be opened safely: {relative.as_posix()}") from exc
    stream: Any | None = None
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse(opened)
            or getattr(opened, "st_nlink", 1) not in {0, 1}
            or _stat_identity(opened) != validated_identity
        ):
            raise ReleaseGateError(f"{context} opened file identity does not match validated path")
        if opened.st_size > max_bytes:
            raise ReleaseGateError(f"{context} file exceeds bounded size limit")
        before = _stat_content_signature(opened)
        _assert_path_snapshots(snapshots, context=context)
        stream = os.fdopen(descriptor, "rb", closefd=True)
        descriptor = -1
        yield stream
        after = os.fstat(stream.fileno())
        if _stat_content_signature(after) != before:
            raise ReleaseGateError(f"{context} file changed during inspection")
        _assert_path_snapshots(snapshots, context=context)
    finally:
        if stream is not None:
            stream.close()
        elif descriptor >= 0:
            os.close(descriptor)


def _secure_read_bytes(
    root: Path,
    relative: PurePosixPath,
    *,
    context: str,
    max_bytes: int = _MAX_PUBLISHABLE_FILE_BYTES,
    expected_identity: tuple[Any, ...] | None = None,
) -> bytes:
    with _secure_open_regular(
        root,
        relative,
        context=context,
        max_bytes=max_bytes,
        expected_identity=expected_identity,
    ) as stream:
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = stream.read(min(1024 * 1024, max_bytes - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                raise ReleaseGateError(f"{context} file exceeds bounded size limit")
            chunks.append(chunk)
        return b"".join(chunks)


def _load_json_file(root: Path, relative: PurePosixPath) -> Mapping[str, Any]:
    document = _load_json_bytes(
        _secure_read_bytes(root, relative, context="JSON evidence"),
        source=relative.as_posix(),
    )
    if not isinstance(document, Mapping):
        raise ReleaseGateError(f"JSON evidence must be an object: {relative.as_posix()}")
    return document


def _canonical_origin(repository: Path) -> str:
    origin = str(_git(repository, "remote", "get-url", "origin")).strip()
    if not origin or any(character in origin for character in "\r\n\0"):
        raise ReleaseGateError("repository origin is invalid")
    if re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", origin, re.IGNORECASE):
        return origin.removesuffix(".git").casefold()
    if re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", origin, re.IGNORECASE):
        path = origin.split(":", 1)[1].removesuffix(".git")
        return f"https://github.com/{path}".casefold()
    raise ReleaseGateError("repository origin is not the bound GitHub repository")


def _directory_path_identity(path: Path, *, context: str) -> tuple[int, ...]:
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ReleaseGateError(f"{context} identity is unavailable") from exc
    if (
        resolved != path
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
    ):
        raise ReleaseGateError(f"{context} contains a link, reparse, or redirect")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        getattr(metadata, "st_birthtime_ns", metadata.st_ctime_ns),
        metadata.st_mode,
    )


def _candidate_owner_binding(
    candidate: Path,
    outputs: Path,
    owner_repository: Path | None,
) -> Path:
    if owner_repository is None:
        raise ReleaseGateError("candidate mode requires --owner-repo")
    try:
        owner = Path(owner_repository).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ReleaseGateError("candidate owner repository is unavailable") from exc
    _directory_path_identity(owner, context="candidate owner repository")
    container = owner / ".cutover-candidate"
    _directory_path_identity(container, context="candidate owner container")
    if candidate == container or container not in candidate.parents:
        raise ReleaseGateError("candidate repository must be strictly below owner/.cutover-candidate")
    current = container
    for part in candidate.relative_to(container).parts:
        current = current / part
        _directory_path_identity(current, context="candidate root chain")
    if outputs != owner / "outputs":
        raise ReleaseGateError("candidate outputs root must be the exact owner outputs directory")
    if _canonical_origin(candidate) != _canonical_origin(owner):
        raise ReleaseGateError("candidate and owner origins do not match")
    owner_state, _owner_fingerprint = _dirty_tree_fingerprint(owner)
    if owner_state != "clean":
        raise ReleaseGateError("candidate owner repository must be clean")
    return owner


def _validate_repository(
    repository: Path,
    outputs_root: Path,
    tree_mode: TreeMode,
    *,
    owner_repository: Path | None = None,
) -> tuple[Path, Path, str]:
    root = Path(repository).resolve()
    outputs = Path(outputs_root).resolve()
    if tree_mode not in {"working-pre-cutover", "candidate", "final"}:
        raise ReleaseGateError(f"unsupported tree mode: {tree_mode}")
    if not root.is_dir() or not (root / ".git").exists():
        raise ReleaseGateError(f"repository does not exist or is not a Git worktree: {root}")
    if not outputs.is_dir():
        raise ReleaseGateError(f"verified outputs root does not exist: {outputs}")
    owner: Path | None = None
    if tree_mode == "candidate":
        owner = _candidate_owner_binding(root, outputs, owner_repository)
    elif owner_repository is not None:
        raise ReleaseGateError("owner repository is valid only in candidate mode")
    elif outputs != root / "outputs":
        raise ReleaseGateError("verified outputs root must be the canonical repository outputs directory")
    _validate_git_binding(root)
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if str(status).strip():
        raise ReleaseGateError("release gate refuses a dirty repository")
    commit_oid = str(_git(root, "rev-parse", "HEAD")).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit_oid):
        raise ReleaseGateError("repository HEAD is not a full commit OID")
    if tree_mode == "candidate":
        symbolic = _git_completed(root, "symbolic-ref", "-q", "HEAD", check=False)
        if symbolic.returncode == 0:
            raise ReleaseGateError("candidate mode requires a detached candidate tree")
        _outputs_inventory_sha256(root, outputs)
        if owner is None:
            raise ReleaseGateError("candidate owner repository binding is unavailable")
        if str(_git(owner, "status", "--porcelain=v1", "--untracked-files=all")).strip():
            raise ReleaseGateError("candidate owner repository must be clean")
    return root, outputs, commit_oid


def _runtime_relative_path(value: object, *, context: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ReleaseGateError(f"{context} path is invalid")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ReleaseGateError(f"{context} path is invalid")
    return relative


def _runtime_tree_index(
    root: Path,
    *,
    context: str,
) -> dict[str, tuple[Path, os.stat_result]]:
    if root.resolve(strict=True) != root:
        raise ReleaseGateError(f"{context} root is redirected")
    rows = _walk_regular_tree(root, context=context)
    return {relative: (path, metadata) for relative, path, metadata in rows}


def _runtime_source_digest(inventory: object) -> str:
    encoded = json.dumps(
        inventory,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _assert_active_repository_snapshot(
    repository: Path,
    *,
    commit_oid: str,
    tree_oid: str,
) -> None:
    if (
        str(_git(repository, "rev-parse", "HEAD")).strip() != commit_oid
        or str(_git(repository, "rev-parse", "HEAD^{tree}")).strip() != tree_oid
        or str(_git(repository, "rev-parse", f"{commit_oid}^{{tree}}")).strip()
        != tree_oid
        or str(_git(repository, "status", "--porcelain=v1", "--untracked-files=all"))
    ):
        raise ReleaseGateError("active runtime repository snapshot changed")


def _git_blob_command(repository: Path, argument: str) -> tuple[str, ...]:
    return ("git", "-C", str(repository), "cat-file", argument)


def _run_git_blob_batch(
    repository: Path,
    argument: str,
    requests: bytes,
    *,
    maximum: int,
    timeout: float = 60,
) -> bytes:
    if maximum < 0 or timeout <= 0 or len(requests) > _MAX_ARCHIVE_MEMBERS * 41:
        raise ReleaseGateError("active runtime Git blob batch is invalid")
    target_command = _git_blob_command(repository, argument)
    launch_header = json.dumps(
        list(target_command),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    if len(launch_header) > 65_536:
        raise ReleaseGateError("active runtime Git blob batch is invalid")
    launch_input = launch_header + requests
    platform_options: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process: subprocess.Popen[bytes] | None = None
    lease: _ProcessTreeLease | None = None
    writer: threading.Thread | None = None
    writer_started = False
    readers: list[threading.Thread] = []
    started_readers: list[threading.Thread] = []
    stdout = bytearray()
    stderr = bytearray()
    stdout_oversized = threading.Event()
    stderr_oversized = threading.Event()
    transport_errors: list[BaseException] = []
    timed_out = False
    returncode: int | None = None

    def terminate_process() -> None:
        if process is None:
            return
        try:
            process.kill()
        except OSError:
            pass

    def drain(
        stream: Any,
        target: bytearray,
        limit: int,
        oversized: threading.Event,
    ) -> None:
        try:
            while True:
                remaining = limit + 1 - len(target)
                if remaining <= 0:
                    oversized.set()
                    terminate_process()
                    return
                chunk = stream.read(min(8192, remaining))
                if not chunk:
                    return
                target.extend(chunk)
                if len(target) > limit:
                    oversized.set()
                    terminate_process()
                    return
        except (OSError, ValueError) as exc:
            transport_errors.append(exc)
            terminate_process()

    def write_requests() -> None:
        if process is None or process.stdin is None:
            return
        try:
            process.stdin.write(launch_input)
            process.stdin.flush()
        except BrokenPipeError:
            pass
        except (OSError, ValueError) as exc:
            transport_errors.append(exc)
            terminate_process()
        finally:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass

    try:
        if os.name != "nt":
            _enable_posix_subreaper()
        baseline = _linux_direct_children()
        process = subprocess.Popen(
            (
                _process_tree_gate_interpreter(sys.executable),
                "-I",
                "-S",
                "-B",
                "-c",
                _GIT_BLOB_BATCH_LAUNCHER,
            ),
            cwd=repository,
            env=_base_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            **platform_options,
        )
        lease = _ProcessTreeLease(process, baseline)
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise OSError("active runtime Git blob batch pipes are unavailable")
        readers = [
            threading.Thread(
                target=drain,
                args=(process.stdout, stdout, maximum, stdout_oversized),
                daemon=True,
            ),
            threading.Thread(
                target=drain,
                args=(process.stderr, stderr, 64 * 1024, stderr_oversized),
                daemon=True,
            ),
        ]
        for reader in readers:
            reader.start()
            started_readers.append(reader)
        writer = threading.Thread(target=write_requests, daemon=True)
        writer.start()
        writer_started = True
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReleaseGateError("active runtime Git blob batch is invalid") from exc
    finally:
        if process is not None:
            if lease is not None:
                lease.terminate_remaining()
            elif process.poll() is None:
                process.kill()
                process.wait(timeout=30)
        joiners = (
            [writer] if writer is not None and writer_started else []
        ) + started_readers
        for thread in joiners:
            thread.join(timeout=30)
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
    if any(
        thread.is_alive()
        for thread in (
            [writer] if writer is not None and writer_started else []
        )
        + started_readers
    ):
        raise ReleaseGateError("active runtime Git blob batch transport did not terminate")
    if stdout_oversized.is_set():
        raise ReleaseGateError("active runtime Git blob batch stdout exceeded size limit")
    if stderr_oversized.is_set():
        raise ReleaseGateError("active runtime Git blob batch stderr exceeded size limit")
    if timed_out:
        raise ReleaseGateError("active runtime Git blob batch timed out")
    if transport_errors:
        raise ReleaseGateError("active runtime Git blob batch transport is invalid")
    if returncode != 0:
        raise ReleaseGateError("active runtime Git blob batch exited nonzero")
    if len(stdout) > maximum or len(stderr) > 64 * 1024:
        raise ReleaseGateError("active runtime Git blob batch is invalid")
    return bytes(stdout)


def _git_blob_payloads(
    repository: Path,
    git_entries: Sequence[Mapping[str, str]],
) -> dict[str, bytes]:
    if len(git_entries) > _MAX_ARCHIVE_MEMBERS:
        raise ReleaseGateError("active runtime Git blob batch is invalid")
    paths: set[str] = set()
    object_oids: list[str] = []
    seen_oids: set[str] = set()
    for entry in git_entries:
        path = entry.get("path")
        oid = entry.get("blob_oid")
        if (
            not isinstance(path, str)
            or path in paths
            or re.fullmatch(r"[0-9a-f]{40}", str(oid)) is None
        ):
            raise ReleaseGateError("active runtime Git blob batch is invalid")
        paths.add(path)
        normalized_oid = str(oid)
        if normalized_oid not in seen_oids:
            seen_oids.add(normalized_oid)
            object_oids.append(normalized_oid)
    requests = b"".join(f"{oid}\n".encode("ascii") for oid in object_oids)
    checked = _run_git_blob_batch(
        repository,
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        requests,
        maximum=len(object_oids) * 96,
    )
    lines = checked.split(b"\n")
    if not lines or lines[-1] != b"" or len(lines) != len(object_oids) + 1:
        raise ReleaseGateError("active runtime Git blob batch is invalid")
    sizes: dict[str, int] = {}
    for oid, line in zip(object_oids, lines[:-1], strict=True):
        try:
            fields = line.decode("ascii").split(" ")
        except UnicodeError as exc:
            raise ReleaseGateError("active runtime Git blob batch is invalid") from exc
        if (
            len(fields) != 3
            or fields[0] != oid
            or fields[1] != "blob"
            or re.fullmatch(r"0|[1-9][0-9]*", fields[2]) is None
            or line != f"{oid} blob {fields[2]}".encode("ascii")
        ):
            raise ReleaseGateError("active runtime Git blob batch is invalid")
        size = int(fields[2])
        if size > _MAX_ARCHIVE_MEMBER_BYTES:
            raise ReleaseGateError("active runtime Git blob batch is invalid")
        sizes[oid] = size
    total_size = sum(sizes[str(entry["blob_oid"])] for entry in git_entries)
    if total_size > _MAX_PUBLISHABLE_FILE_BYTES:
        raise ReleaseGateError("active runtime Git blob batch is invalid")
    batch = _run_git_blob_batch(
        repository,
        "--batch",
        requests,
        maximum=sum(sizes.values()) + len(object_oids) * 96,
    )
    offset = 0
    blobs: dict[str, bytes] = {}
    for oid in object_oids:
        size = sizes[oid]
        header = f"{oid} blob {size}\n".encode("ascii")
        if batch[offset : offset + len(header)] != header:
            raise ReleaseGateError("active runtime Git blob batch is invalid")
        offset += len(header)
        end = offset + size
        if end >= len(batch) or batch[end : end + 1] != b"\n":
            raise ReleaseGateError("active runtime Git blob batch is invalid")
        payload = batch[offset:end]
        digest = hashlib.sha1(
            b"blob " + str(size).encode("ascii") + b"\0" + payload,
            usedforsecurity=False,
        ).hexdigest()
        if digest != oid:
            raise ReleaseGateError("active runtime Git blob batch is invalid")
        blobs[oid] = payload
        offset = end + 1
    if offset != len(batch):
        raise ReleaseGateError("active runtime Git blob batch is invalid")
    return {
        str(entry["path"]): blobs[str(entry["blob_oid"])]
        for entry in git_entries
    }


def _active_head_source_inventory(
    repository: Path,
    commit_oid: str,
) -> list[dict[str, str]]:
    listing = str(
        _git(repository, "ls-tree", "-rz", "--full-tree", commit_oid)
    )
    records = listing.split("\0")
    if not records or records[-1] != "":
        raise ReleaseGateError("active runtime HEAD tree is malformed")
    entries: list[dict[str, str]] = []
    modes: dict[str, str] = {}
    for record in records[:-1]:
        header, separator, name = record.partition("\t")
        fields = header.split()
        relative = _runtime_relative_path(name, context="active runtime HEAD")
        if (
            not separator
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
            or re.fullmatch(r"[0-9a-f]{40}", fields[2]) is None
            or relative.as_posix() in modes
        ):
            raise ReleaseGateError("active runtime HEAD tree is malformed")
        modes[relative.as_posix()] = fields[0]
        entries.append(
            {
                "path": relative.as_posix(),
                "git_mode": fields[0],
                "blob_oid": fields[2],
            }
        )
    blob_payloads = _git_blob_payloads(repository, entries)
    archive_source = bytes(
        _git(
            repository,
            "-c",
            "core.autocrlf=false",
            "archive",
            "--format=tar",
            commit_oid,
            text=False,
        )
    )
    if len(archive_source) > _MAX_PUBLISHABLE_FILE_BYTES:
        raise ReleaseGateError("active runtime HEAD archive is oversized")
    payloads: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_source), mode="r:") as archive:
            members = archive.getmembers()
            if len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ReleaseGateError("active runtime HEAD archive is oversized")
            for member in members:
                if member.isdir():
                    continue
                relative = _runtime_relative_path(
                    member.name, context="active runtime HEAD"
                ).as_posix()
                if (
                    not member.isfile()
                    or member.size > _MAX_ARCHIVE_MEMBER_BYTES
                    or relative in payloads
                ):
                    raise ReleaseGateError("active runtime HEAD archive is invalid")
                stream = archive.extractfile(member)
                if stream is None:
                    raise ReleaseGateError("active runtime HEAD archive is invalid")
                payload = stream.read(_MAX_ARCHIVE_MEMBER_BYTES + 1)
                if len(payload) != member.size:
                    raise ReleaseGateError("active runtime HEAD archive is invalid")
                payloads[relative] = payload
    except (tarfile.TarError, OSError) as exc:
        raise ReleaseGateError("active runtime HEAD archive is invalid") from exc
    if set(payloads) != set(modes):
        raise ReleaseGateError("active runtime HEAD archive differs from tree")
    if payloads != blob_payloads:
        raise ReleaseGateError("active runtime HEAD archive differs from tree blobs")
    return [
        {
            "path": relative,
            "sha256": hashlib.sha256(blob_payloads[relative]).hexdigest(),
            "git_mode": modes[relative],
        }
        for relative in sorted(modes)
    ]


def _active_lock_rows(source: bytes) -> list[dict[str, object]]:
    try:
        document = tomllib.loads(source.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseGateError("active runtime selected lock is invalid") from exc
    if (
        not isinstance(document, dict)
        or set(document) != {"lock-version", "created-by", "packages"}
        or document["lock-version"] != "1.0"
        or document["created-by"] != "pip"
        or not isinstance(document["packages"], list)
        or len(document["packages"]) != 43
    ):
        raise ReleaseGateError("active runtime selected lock is invalid")
    rows: list[dict[str, object]] = []
    identities: set[tuple[str, str]] = set()
    for package in document["packages"]:
        if not isinstance(package, dict) or set(package) not in (
            {"name", "version", "wheels"},
            {"name", "version", "wheels", "sdist"},
        ):
            raise ReleaseGateError("active runtime selected lock is invalid")
        name = package["name"]
        version = package["version"]
        wheels = package["wheels"]
        identity = (re.sub(r"[-_.]+", "-", str(name)).casefold(), str(version))
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
            or not isinstance(wheels, list)
            or not wheels
            or identity in identities
        ):
            raise ReleaseGateError("active runtime selected lock is invalid")
        if "sdist" in package:
            sdist = package["sdist"]
            if not isinstance(sdist, dict) or set(sdist) != {
                "name",
                "url",
                "hashes",
            }:
                raise ReleaseGateError("active runtime selected lock is invalid")
            hashes = sdist["hashes"]
            if (
                not isinstance(sdist["name"], str)
                or not sdist["name"]
                or not isinstance(sdist["url"], str)
                or not sdist["url"].startswith("https://")
                or not isinstance(hashes, dict)
                or set(hashes) != {"sha256"}
                or re.fullmatch(r"[0-9a-f]{64}", str(hashes["sha256"])) is None
            ):
                raise ReleaseGateError("active runtime selected lock is invalid")
        candidates: list[dict[str, str]] = []
        candidate_keys: set[tuple[str, str, str]] = set()
        for wheel in wheels:
            if not isinstance(wheel, dict) or set(wheel) != {
                "name",
                "url",
                "hashes",
            }:
                raise ReleaseGateError("active runtime selected lock is invalid")
            hashes = wheel["hashes"]
            if not isinstance(hashes, dict) or set(hashes) != {"sha256"}:
                raise ReleaseGateError("active runtime selected lock is invalid")
            candidate = {
                "name": str(wheel["name"]),
                "url": str(wheel["url"]),
                "sha256": str(hashes["sha256"]),
            }
            key = (candidate["name"], candidate["url"], candidate["sha256"])
            if (
                not isinstance(wheel["name"], str)
                or not candidate["name"].endswith(".whl")
                or not isinstance(wheel["url"], str)
                or not candidate["url"].startswith("https://")
                or re.fullmatch(r"[0-9a-f]{64}", candidate["sha256"]) is None
                or key in candidate_keys
            ):
                raise ReleaseGateError("active runtime selected lock is invalid")
            candidate_keys.add(key)
            candidates.append(candidate)
        identities.add(identity)
        rows.append(
            {
                "identity": identity,
                "name": name,
                "version": version,
                "wheels": candidates,
            }
        )
    if [row["identity"] for row in rows] != sorted(identities):
        raise ReleaseGateError("active runtime selected lock order is invalid")
    return rows


def _active_startup_policy(identity: tuple[str, str]) -> tuple[bool, list[str]]:
    hooks = {
        ("setuptools", "83.0.0"): ["distutils-precedence.pth"],
        ("coverage", "7.15.2"): ["a1_coverage.pth"],
    }.get(identity, [])
    return not hooks, hooks


def _active_wheel_inventory(
    source: bytes,
    *,
    allowed_startup_surfaces: frozenset[str] = frozenset(),
) -> list[dict[str, object]]:
    if len(source) > _MAX_ARCHIVE_TOTAL_BYTES:
        raise ReleaseGateError("active runtime wheel compressed content is oversized")
    rows: list[dict[str, object]] = []
    exact_paths: set[str] = set()
    windows_paths: dict[str, str] = {}
    node_types: dict[str, str] = {}

    try:
        from scripts.run_coverage_gate import (  # noqa: PLC0415
            _is_canonical_repository_component,
        )
    except ImportError as exc:
        raise ReleaseGateError(
            "active runtime portable path policy is unavailable"
        ) from exc

    def canonical_member_path(name: str, *, directory: bool) -> tuple[str, str]:
        if (
            not name
            or any(ord(character) < 32 or ord(character) == 127 for character in name)
            or "\\" in name
            or name.startswith(("/", "//"))
            or re.match(r"^[A-Za-z]:", name)
        ):
            raise ReleaseGateError("active runtime wheel member path is invalid")
        candidate = name[:-1] if directory else name
        parts = candidate.split("/")
        if (
            not candidate
            or any(
                not _is_canonical_repository_component(part) for part in parts
            )
            or any(unicodedata.normalize("NFC", part) != part for part in parts)
        ):
            raise ReleaseGateError("active runtime wheel member path is invalid")
        normalized = "/".join(parts)
        windows_key = "/".join(
            unicodedata.normalize("NFC", part).casefold() for part in parts
        )
        if normalized in exact_paths:
            raise ReleaseGateError("active runtime wheel has a duplicate member")
        previous = windows_paths.get(windows_key)
        if previous is not None and previous != normalized:
            raise ReleaseGateError("active runtime wheel has a Windows path collision")
        for index in range(1, len(parts)):
            prefix = "/".join(
                unicodedata.normalize("NFC", part).casefold()
                for part in parts[:index]
            )
            if node_types.get(prefix) == "file":
                raise ReleaseGateError("active runtime wheel has a prefix collision")
            node_types.setdefault(prefix, "directory")
        kind = "directory" if directory else "file"
        existing = node_types.get(windows_key)
        if existing is not None and existing != kind:
            raise ReleaseGateError("active runtime wheel has a file-directory collision")
        node_types[windows_key] = kind
        exact_paths.add(normalized)
        windows_paths[windows_key] = normalized
        return normalized, windows_key

    def bind_local_header(
        info: zipfile.ZipInfo,
        *,
        central_name: bytes,
        central_directory_offset: int,
    ) -> tuple[int, int]:
        offset = info.header_offset
        fixed_end = offset + 30
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or offset < 0
            or fixed_end > central_directory_offset
            or source[offset:offset + 4] != b"PK\x03\x04"
        ):
            raise ReleaseGateError("active runtime wheel local header is invalid")
        local_flags = int.from_bytes(source[offset + 6:offset + 8], "little")
        local_method = int.from_bytes(source[offset + 8:offset + 10], "little")
        local_crc = int.from_bytes(source[offset + 14:offset + 18], "little")
        local_compressed_size = int.from_bytes(
            source[offset + 18:offset + 22], "little"
        )
        local_file_size = int.from_bytes(source[offset + 22:offset + 26], "little")
        name_length = int.from_bytes(source[offset + 26:offset + 28], "little")
        extra_length = int.from_bytes(source[offset + 28:offset + 30], "little")
        name_end = fixed_end + name_length
        payload_offset = name_end + extra_length
        payload_end = payload_offset + info.compress_size
        if (
            name_length > _MAX_ZIP_MEMBER_NAME_BYTES
            or extra_length != 0
            or name_end > central_directory_offset
            or payload_offset > central_directory_offset
            or payload_end > central_directory_offset
        ):
            raise ReleaseGateError("active runtime wheel local header is invalid")
        encoding = "utf-8" if info.flag_bits & 0x800 else "cp437"
        local_name = source[fixed_end:name_end]
        try:
            decoded_name = local_name.decode(encoding)
            canonical_name = info.orig_filename.encode(encoding)
        except UnicodeError as exc:
            raise ReleaseGateError(
                "active runtime wheel local filename is invalid"
            ) from exc
        supported_flags = 0x800 | (0x6 if info.compress_type == zipfile.ZIP_DEFLATED else 0)
        if (
            local_flags != info.flag_bits
            or info.flag_bits & (0x1 | 0x8)
            or info.flag_bits & ~supported_flags
            or local_method != info.compress_type
            or local_method not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
            or name_length != len(central_name)
            or local_name != central_name
            or central_name != canonical_name
            or decoded_name != info.orig_filename
            or local_crc != info.CRC
            or local_compressed_size != info.compress_size
            or local_file_size != info.file_size
        ):
            raise ReleaseGateError("active runtime wheel local header differs")
        return offset, payload_end

    def bind_central_directory(
        infos: Sequence[zipfile.ZipInfo],
        *,
        central_directory_offset: int,
        archive_comment: bytes,
    ) -> list[bytes]:
        cursor = central_directory_offset
        names: list[bytes] = []
        for info in infos:
            fixed_end = cursor + 46
            if (
                fixed_end > len(source)
                or source[cursor:cursor + 4] != b"PK\x01\x02"
            ):
                raise ReleaseGateError(
                    "active runtime wheel central header is invalid"
                )
            flags = int.from_bytes(source[cursor + 8:cursor + 10], "little")
            method = int.from_bytes(source[cursor + 10:cursor + 12], "little")
            crc = int.from_bytes(source[cursor + 16:cursor + 20], "little")
            compressed_size = int.from_bytes(
                source[cursor + 20:cursor + 24], "little"
            )
            file_size = int.from_bytes(source[cursor + 24:cursor + 28], "little")
            name_length = int.from_bytes(source[cursor + 28:cursor + 30], "little")
            extra_length = int.from_bytes(source[cursor + 30:cursor + 32], "little")
            comment_length = int.from_bytes(source[cursor + 32:cursor + 34], "little")
            disk_number = int.from_bytes(source[cursor + 34:cursor + 36], "little")
            internal_attr = int.from_bytes(source[cursor + 36:cursor + 38], "little")
            external_attr = int.from_bytes(source[cursor + 38:cursor + 42], "little")
            local_offset = int.from_bytes(source[cursor + 42:cursor + 46], "little")
            name_end = fixed_end + name_length
            extra_end = name_end + extra_length
            record_end = extra_end + comment_length
            if (
                name_length > _MAX_ZIP_MEMBER_NAME_BYTES
                or extra_length != 0
                or comment_length != 0
                or record_end > len(source)
            ):
                raise ReleaseGateError(
                    "active runtime wheel central header is invalid"
                )
            raw_name = source[fixed_end:name_end]
            encoding = "utf-8" if flags & 0x800 else "cp437"
            try:
                decoded_name = raw_name.decode(encoding)
                canonical_name = info.orig_filename.encode(encoding)
            except UnicodeError as exc:
                raise ReleaseGateError(
                    "active runtime wheel central filename is invalid"
                ) from exc
            if (
                flags != info.flag_bits
                or method != info.compress_type
                or crc != info.CRC
                or compressed_size != info.compress_size
                or file_size != info.file_size
                or disk_number != 0
                or internal_attr != info.internal_attr
                or external_attr != info.external_attr
                or local_offset != info.header_offset
                or raw_name != canonical_name
                or decoded_name != info.orig_filename
                or source[name_end:extra_end] != info.extra
                or info.comment != b""
                or source[extra_end:record_end] != info.comment
            ):
                raise ReleaseGateError("active runtime wheel central header differs")
            names.append(raw_name)
            cursor = record_end
        eocd_end = cursor + 22
        if (
            eocd_end > len(source)
            or source[cursor:cursor + 4] != b"PK\x05\x06"
        ):
            raise ReleaseGateError("active runtime wheel end record is invalid")
        disk_number = int.from_bytes(source[cursor + 4:cursor + 6], "little")
        central_disk = int.from_bytes(source[cursor + 6:cursor + 8], "little")
        disk_members = int.from_bytes(source[cursor + 8:cursor + 10], "little")
        total_members = int.from_bytes(source[cursor + 10:cursor + 12], "little")
        central_size = int.from_bytes(source[cursor + 12:cursor + 16], "little")
        central_offset = int.from_bytes(source[cursor + 16:cursor + 20], "little")
        comment_length = int.from_bytes(source[cursor + 20:cursor + 22], "little")
        if (
            disk_number != 0
            or central_disk != 0
            or disk_members != len(infos)
            or total_members != len(infos)
            or central_size != cursor - central_directory_offset
            or central_offset != central_directory_offset
            or comment_length != 0
            or archive_comment != b""
            or comment_length != len(archive_comment)
            or eocd_end + comment_length != len(source)
            or source[eocd_end:] != archive_comment
        ):
            raise ReleaseGateError("active runtime wheel end record differs")
        return names

    try:
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            infos = archive.infolist()
            central_directory_offset = archive.start_dir
            if (
                len(infos) > _MAX_ARCHIVE_MEMBERS
                or not isinstance(central_directory_offset, int)
                or isinstance(central_directory_offset, bool)
                or central_directory_offset < 0
                or central_directory_offset > len(source)
            ):
                raise ReleaseGateError("active runtime wheel member count is oversized")
            central_names = bind_central_directory(
                infos,
                central_directory_offset=central_directory_offset,
                archive_comment=archive.comment,
            )
            validated: list[tuple[zipfile.ZipInfo, str]] = []
            local_spans: list[tuple[int, int]] = []
            total_declared = 0
            for info, central_name in zip(infos, central_names, strict=True):
                raw_name = info.orig_filename
                directory = raw_name.endswith("/")
                normalized, _windows_key = canonical_member_path(
                    raw_name,
                    directory=directory,
                )
                mode = info.external_attr >> 16
                member_type = stat.S_IFMT(mode)
                if (
                    stat.S_ISLNK(mode)
                    or member_type not in {0, stat.S_IFREG, stat.S_IFDIR}
                    or (directory and member_type not in {0, stat.S_IFDIR})
                    or (not directory and member_type == stat.S_IFDIR)
                ):
                    raise ReleaseGateError("active runtime wheel member is not regular")
                local_spans.append(
                    bind_local_header(
                        info,
                        central_name=central_name,
                        central_directory_offset=central_directory_offset,
                    )
                )
                if info.flag_bits & 0x1:
                    raise ReleaseGateError("active runtime wheel member is encrypted")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise ReleaseGateError(
                        "active runtime wheel compression method is unsupported"
                    )
                if directory:
                    if info.CRC != 0 or info.compress_size != 0 or info.file_size != 0:
                        raise ReleaseGateError(
                            "active runtime wheel directory payload is invalid"
                        )
                    continue
                total_declared += info.file_size
                if (
                    info.file_size > _MAX_ARCHIVE_TOTAL_BYTES
                    or total_declared > _MAX_ARCHIVE_TOTAL_BYTES
                    or (info.file_size and info.compress_size == 0)
                    or (
                        info.compress_size
                        and info.file_size / info.compress_size
                        > _MAX_ARCHIVE_COMPRESSION_RATIO
                    )
                    or (
                        PurePosixPath(normalized).name.casefold().endswith(
                            (".pth", ".egg-link")
                        )
                        or PurePosixPath(normalized).name.casefold()
                        in {"sitecustomize.py", "usercustomize.py"}
                    )
                    and normalized not in allowed_startup_surfaces
                ):
                    raise ReleaseGateError("active runtime wheel is invalid")
                validated.append((info, normalized))
            ordered_spans = sorted(local_spans)
            if (
                not ordered_spans
                or ordered_spans[0][0] != 0
                or ordered_spans[-1][1] != central_directory_offset
                or any(
                    previous_end != current_start
                    for (_previous_start, previous_end), (current_start, _current_end)
                    in zip(ordered_spans, ordered_spans[1:], strict=False)
                )
            ):
                raise ReleaseGateError("active runtime wheel local layout is invalid")
            if total_declared and (
                not source
                or total_declared / len(source) > _MAX_ARCHIVE_COMPRESSION_RATIO
            ):
                raise ReleaseGateError("active runtime wheel compression ratio is invalid")
            for info, normalized in validated:
                with archive.open(info, "r") as stream:
                    chunks: list[bytes] = []
                    size = 0
                    while True:
                        chunk = stream.read(min(1024 * 1024, info.file_size - size + 1))
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > info.file_size or size > _MAX_ARCHIVE_TOTAL_BYTES:
                            raise ReleaseGateError("active runtime wheel member is oversized")
                        chunks.append(chunk)
                payload = b"".join(chunks)
                if size != info.file_size:
                    raise ReleaseGateError("active runtime wheel is invalid")
                rows.append(
                    {
                        "path": normalized,
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
    except (NotImplementedError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ReleaseGateError("active runtime wheel is invalid") from exc
    return sorted(rows, key=lambda row: str(row["path"]))


def _assert_active_wheel_identity(
    source: bytes,
    *,
    filename: str,
    expected_name: str,
    expected_version: str,
    require_py3_none_any: bool,
) -> None:
    try:
        parsed_name, parsed_version, parsed_build, parsed_tags = parse_wheel_filename(
            filename
        )
    except InvalidWheelFilename as exc:
        raise ReleaseGateError("active runtime wheel filename is invalid") from exc
    filename_fields = filename[:-4].split("-")
    normalized_name = canonicalize_name(expected_name)
    distribution_token = normalized_name.replace("-", "_")
    if (
        filename != filename.casefold()
        or not filename.endswith(".whl")
        or len(filename_fields) not in {5, 6}
        or filename_fields[0] != distribution_token
        or filename_fields[1] != expected_version
        or canonicalize_name(str(parsed_name)) != normalized_name
        or str(parsed_version) != expected_version
        or not parsed_tags
        or (
            require_py3_none_any
            and set(parsed_tags) != set(parse_tag("py3-none-any"))
        )
    ):
        raise ReleaseGateError("active runtime wheel filename identity is invalid")
    expected_dist_info = f"{distribution_token}-{expected_version}.dist-info"
    try:
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            names = archive.namelist()
            dist_info_roots = {
                PurePosixPath(name).parts[0]
                for name in names
                if PurePosixPath(name).parts
                and PurePosixPath(name).parts[0].endswith(".dist-info")
            }
            metadata_name = f"{expected_dist_info}/METADATA"
            wheel_name = f"{expected_dist_info}/WHEEL"
            if (
                dist_info_roots != {expected_dist_info}
                or names.count(metadata_name) != 1
                or names.count(wheel_name) != 1
            ):
                raise ReleaseGateError("active runtime wheel dist-info identity is invalid")
            metadata_source = archive.read(metadata_name).decode("utf-8")
            wheel_source = archive.read(wheel_name).decode("utf-8")
    except (
        KeyError,
        NotImplementedError,
        RuntimeError,
        UnicodeError,
        zipfile.BadZipFile,
    ) as exc:
        raise ReleaseGateError("active runtime wheel identity is invalid") from exc
    metadata = Parser().parsestr(metadata_source)
    wheel = Parser().parsestr(wheel_source)
    metadata_core_versions = metadata.get_all("Metadata-Version", [])
    metadata_names = metadata.get_all("Name", [])
    metadata_versions = metadata.get_all("Version", [])
    if (
        len(metadata_core_versions) != 1
        or metadata_core_versions[0] not in _SUPPORTED_CORE_METADATA_VERSIONS
        or len(metadata_names) != 1
        or canonicalize_name(metadata_names[0]) != normalized_name
        or metadata_versions != [expected_version]
        or bool(metadata.defects)
        or metadata.is_multipart()
        or not isinstance(metadata.get_payload(), str)
    ):
        raise ReleaseGateError("active runtime wheel metadata identity is invalid")
    raw_wheel_headers = [name.casefold() for name, _value in wheel.raw_items()]
    allowed_headers = {
        "build",
        "generator",
        "root-is-purelib",
        "tag",
        "wheel-version",
    }
    wheel_versions = wheel.get_all("Wheel-Version", [])
    roots = wheel.get_all("Root-Is-Purelib", [])
    wheel_tags = wheel.get_all("Tag", [])
    wheel_builds = wheel.get_all("Build", [])
    generators = wheel.get_all("Generator", [])
    if (
        any(name not in allowed_headers for name in raw_wheel_headers)
        or wheel_versions != ["1.0"]
        or len(roots) != 1
        or len(wheel_tags) != len(set(wheel_tags))
        or not wheel_tags
        or len(wheel_builds) > 1
        or len(generators) > 1
        or bool(str(wheel.get_payload()).strip())
    ):
        raise ReleaseGateError("active runtime WHEEL headers are invalid")
    try:
        metadata_tags = set().union(*(parse_tag(value) for value in wheel_tags))
    except ValueError as exc:
        raise ReleaseGateError("active runtime WHEEL tags are invalid") from exc
    expected_builds = (
        [f"{parsed_build[0]}{parsed_build[1]}"] if parsed_build else []
    )
    pure_tags = all(
        tag.abi == "none" and tag.platform == "any" for tag in parsed_tags
    )
    expected_root = "true" if pure_tags else "false"
    if (
        metadata_tags != set(parsed_tags)
        or wheel_builds != expected_builds
        or roots != [expected_root]
        or (require_py3_none_any and roots != ["true"])
    ):
        raise ReleaseGateError("active runtime WHEEL identity is invalid")


def _active_project_version(source_root: Path) -> str:
    source = _secure_read_bytes(
        source_root,
        PurePosixPath("src/hsconfig/version.py"),
        context="active runtime project version",
    )
    try:
        tree = ast.parse(source)
    except (SyntaxError, UnicodeError) as exc:
        raise ReleaseGateError("active runtime project version is invalid") from exc
    values = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "__version__"
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    ]
    if len(values) != 1:
        raise ReleaseGateError("active runtime project version is invalid")
    return values[0]


def _assert_active_local_project(
    local: object,
    *,
    manifest_root: Path,
    source_root: Path,
    inventory_digest: str,
) -> None:
    if not isinstance(local, dict) or set(local) != {
        "name",
        "version",
        "wheel_path",
        "sha256",
        "files",
        "source_inventory_sha256",
    }:
        raise ReleaseGateError("active runtime local project schema is invalid")
    version = _active_project_version(source_root)
    digest = local["sha256"]
    local_root = manifest_root / "local-wheel"
    wheel_path = Path(str(local["wheel_path"])).absolute()
    if (
        local["name"] != "hsconfig"
        or local["version"] != version
        or local["source_inventory_sha256"] != inventory_digest
        or re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None
        or wheel_path.parent != local_root
        or wheel_path.resolve(strict=True) != wheel_path
        or wheel_path.suffix != ".whl"
    ):
        raise ReleaseGateError("active runtime local project binding is invalid")
    local_index = _runtime_tree_index(
        local_root,
        context="active runtime local wheel",
    )
    if set(local_index) != {wheel_path.name}:
        raise ReleaseGateError("active runtime local wheel closure is invalid")
    wheel_source = _secure_read_bytes(
        local_root,
        _runtime_relative_path(wheel_path.name, context="active runtime local wheel"),
        context="active runtime local wheel",
        expected_identity=_stat_identity(local_index[wheel_path.name][1]),
    )
    if hashlib.sha256(wheel_source).hexdigest() != digest:
        raise ReleaseGateError("active runtime local wheel changed")
    inventory = _active_wheel_inventory(wheel_source)
    if local["files"] != inventory:
        raise ReleaseGateError("active runtime local wheel inventory changed")
    _assert_active_wheel_identity(
        wheel_source,
        filename=wheel_path.name,
        expected_name="hsconfig",
        expected_version=version,
        require_py3_none_any=True,
    )


def _runtime_artifact_inventory(
    artifacts: object,
    *,
    manifest_root: Path,
    lock_rows: Sequence[Mapping[str, object]],
) -> dict[str, tuple[int, str]]:
    if not isinstance(artifacts, list) or len(artifacts) != len(lock_rows):
        raise ReleaseGateError("active runtime artifact set is invalid")
    expected_overlay: dict[str, tuple[int, str]] = {}
    identities: set[tuple[str, str]] = set()
    install_values: set[bool] = set()
    observed_order: list[tuple[str, str]] = []
    for artifact, locked in zip(artifacts, lock_rows, strict=True):
        if not isinstance(artifact, dict) or set(artifact) != {
            "name",
            "version",
            "url",
            "sha256",
            "wheel_path",
            "files",
            "install",
            "allowed_startup_surfaces",
        }:
            raise ReleaseGateError("active runtime artifact schema is invalid")
        name = artifact["name"]
        version = artifact["version"]
        url = artifact["url"]
        digest = artifact["sha256"]
        install = artifact["install"]
        files = artifact["files"]
        allowed = artifact["allowed_startup_surfaces"]
        identity = (re.sub(r"[-_.]+", "-", str(name)).casefold(), str(version))
        expected_install, expected_allowed = _active_startup_policy(identity)
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
            or not isinstance(url, str)
            or not url
            or re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None
            or not isinstance(install, bool)
            or not isinstance(files, list)
            or not isinstance(allowed, list)
            or any(not isinstance(value, str) for value in allowed)
            or len(set(allowed)) != len(allowed)
            or identity in identities
            or identity != locked["identity"]
            or name != locked["name"]
            or version != locked["version"]
            or install is not expected_install
            or allowed != expected_allowed
        ):
            raise ReleaseGateError("active runtime artifact schema is invalid")
        identities.add(identity)
        observed_order.append(identity)
        install_values.add(install)
        wheel_path = Path(str(artifact["wheel_path"]))
        try:
            wheel_relative = PurePosixPath(
                wheel_path.relative_to(manifest_root).as_posix()
            )
        except (TypeError, ValueError) as exc:
            raise ReleaseGateError("active runtime artifact path is invalid") from exc
        wheel_source = _secure_read_bytes(
            manifest_root,
            wheel_relative,
            context="active runtime artifact",
        )
        if hashlib.sha256(wheel_source).hexdigest() != digest:
            raise ReleaseGateError("active runtime artifact changed")
        candidates = locked["wheels"]
        if not isinstance(candidates, list) or not any(
            isinstance(candidate, dict)
            and candidate.get("name") == wheel_path.name
            and candidate.get("url") == url
            and candidate.get("sha256") == digest
            for candidate in candidates
        ):
            raise ReleaseGateError("active runtime artifact is not selected by lock")
        allowed_paths = {
            _runtime_relative_path(value, context="active runtime artifact").as_posix()
            for value in allowed
        }
        artifact_paths: set[str] = set()
        normalized_files: list[dict[str, object]] = []
        for row in files:
            if not isinstance(row, dict) or set(row) != {"path", "size", "sha256"}:
                raise ReleaseGateError("active runtime artifact inventory is invalid")
            relative = _runtime_relative_path(
                row["path"], context="active runtime artifact"
            ).as_posix()
            size = row["size"]
            row_digest = row["sha256"]
            if (
                relative in artifact_paths
                or not isinstance(size, int)
                or isinstance(size, bool)
                or size < 0
                or re.fullmatch(r"[0-9a-f]{64}", str(row_digest)) is None
            ):
                raise ReleaseGateError("active runtime artifact inventory is invalid")
            artifact_paths.add(relative)
            normalized_files.append(dict(row))
            if not install and relative not in allowed_paths:
                if relative in expected_overlay:
                    raise ReleaseGateError("active runtime overlay paths collide")
                expected_overlay[relative] = (size, str(row_digest))
        if normalized_files != sorted(
            normalized_files, key=lambda row: str(row["path"])
        ) or not allowed_paths.issubset(artifact_paths):
            raise ReleaseGateError("active runtime artifact inventory is invalid")
        if _active_wheel_inventory(
            wheel_source,
            allowed_startup_surfaces=frozenset(expected_allowed),
        ) != normalized_files:
            raise ReleaseGateError("active runtime artifact inventory changed")
        _assert_active_wheel_identity(
            wheel_source,
            filename=wheel_path.name,
            expected_name=str(name),
            expected_version=str(version),
            require_py3_none_any=False,
        )
    if install_values != {False, True}:
        raise ReleaseGateError("active runtime artifact policy is incomplete")
    if observed_order != [row["identity"] for row in lock_rows]:
        raise ReleaseGateError("active runtime artifact order is invalid")
    return expected_overlay


def _assert_runtime_tree_payloads(
    root: Path,
    expected: Mapping[str, tuple[int | None, str]],
    *,
    context: str,
    modes: Mapping[str, str] | None = None,
) -> None:
    for _pass in range(2):
        observed = _runtime_tree_index(root, context=context)
        if set(observed) != set(expected):
            raise ReleaseGateError(f"{context} inventory differs")
        for relative, (expected_size, expected_digest) in expected.items():
            _path, metadata = observed[relative]
            if modes is not None and os.name != "nt":
                expected_mode = 0o755 if modes[relative] == "100755" else 0o644
                if stat.S_IMODE(metadata.st_mode) != expected_mode:
                    raise ReleaseGateError(f"{context} mode differs")
            source = _secure_read_bytes(
                root,
                PurePosixPath(relative),
                context=context,
                expected_identity=_stat_identity(metadata),
            )
            if (
                (expected_size is not None and len(source) != expected_size)
                or hashlib.sha256(source).hexdigest() != expected_digest
            ):
                raise ReleaseGateError(f"{context} payload differs")


def _bound_active_runtime_paths(repository: Path) -> tuple[Path, Path]:
    sentinel = os.environ["HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL"]
    manifest_name = os.environ["HSCONFIG_RUNTIME_MANIFEST"]
    expected_digest = os.environ["HSCONFIG_RUNTIME_MANIFEST_SHA256"]
    if (
        re.fullmatch(r"[0-9a-f]{64}", sentinel) is None
        or re.fullmatch(r"[0-9a-f]{64}", expected_digest) is None
    ):
        raise ReleaseGateError("active runtime binding values are invalid")
    manifest_path = Path(manifest_name).absolute()
    if (
        manifest_path.name != "runtime-manifest.json"
        or manifest_path.resolve(strict=True) != manifest_path
    ):
        raise ReleaseGateError("active runtime binding path is invalid")
    manifest_root = manifest_path.parent
    manifest_source = _secure_read_bytes(
        manifest_root,
        PurePosixPath("runtime-manifest.json"),
        context="active runtime manifest",
        max_bytes=64 * 1024 * 1024,
    )
    if hashlib.sha256(manifest_source).hexdigest() != expected_digest:
        raise ReleaseGateError("active runtime manifest changed")
    document = _load_json_bytes(manifest_source, source="runtime manifest")
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "python_minor",
        "repository",
        "commit_oid",
        "tree_oid",
        "source_inventory",
        "source_inventory_sha256",
        "build_backend_root",
        "environment_root",
        "lock_sha256",
        "sentinel_sha256",
        "artifacts",
        "local_project",
    }:
        raise ReleaseGateError("active runtime manifest schema is invalid")
    repository_root = repository.resolve(strict=True)
    head_oid = str(_git(repository_root, "rev-parse", "HEAD")).strip()
    tree_oid = str(_git(repository_root, "rev-parse", "HEAD^{tree}")).strip()
    if (
        re.fullmatch(r"[0-9a-f]{40}", head_oid) is None
        or re.fullmatch(r"[0-9a-f]{40}", tree_oid) is None
    ):
        raise ReleaseGateError("active runtime repository identity is invalid")
    _assert_active_repository_snapshot(
        repository_root,
        commit_oid=head_oid,
        tree_oid=tree_oid,
    )
    lock_relative = PurePosixPath(
        f"pylock.{sys.version_info.major}.{sys.version_info.minor}.toml"
    )
    source_root = manifest_root / "committed-source"
    build_backend_root = manifest_root / "build-backend"
    lock_source = _secure_read_bytes(
        source_root,
        lock_relative,
        context="active runtime bound selected lock",
        max_bytes=8 * 1024 * 1024,
    )
    lock_rows = _active_lock_rows(lock_source)
    authoritative_inventory = _active_head_source_inventory(
        repository_root,
        head_oid,
    )
    local = document["local_project"]
    inventory = document["source_inventory"]
    inventory_digest = document["source_inventory_sha256"]
    if (
        document["schema_version"] != 1
        or document["python_minor"]
        != f"{sys.version_info.major}.{sys.version_info.minor}"
        or document["repository"] != str(repository_root)
        or re.fullmatch(r"[0-9a-f]{40}", str(document["commit_oid"])) is None
        or re.fullmatch(r"[0-9a-f]{40}", str(document["tree_oid"])) is None
        or re.fullmatch(r"[0-9a-f]{64}", str(document["lock_sha256"])) is None
        or document["commit_oid"] != head_oid
        or document["tree_oid"] != tree_oid
        or document["lock_sha256"] != hashlib.sha256(lock_source).hexdigest()
        or document["build_backend_root"] != str(build_backend_root)
        or Path(str(document["environment_root"])).resolve(strict=True)
        != Path(sys.prefix).resolve(strict=True)
        or document["sentinel_sha256"]
        != hashlib.sha256(sentinel.encode("ascii")).hexdigest()
        or not isinstance(inventory, list)
        or re.fullmatch(r"[0-9a-f]{64}", str(inventory_digest)) is None
        or _runtime_source_digest(inventory) != inventory_digest
    ):
        raise ReleaseGateError("active runtime binding is inconsistent")
    expected_source: dict[str, tuple[int | None, str]] = {}
    source_modes: dict[str, str] = {}
    normalized_inventory: list[dict[str, object]] = []
    for row in inventory:
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "sha256", "git_mode"}
            or row["git_mode"] not in {"100644", "100755"}
            or re.fullmatch(r"[0-9a-f]{64}", str(row["sha256"])) is None
        ):
            raise ReleaseGateError("active runtime source inventory is invalid")
        relative = _runtime_relative_path(
            row["path"], context="active runtime source"
        ).as_posix()
        if relative in expected_source:
            raise ReleaseGateError("active runtime source inventory is invalid")
        expected_source[relative] = (None, str(row["sha256"]))
        source_modes[relative] = str(row["git_mode"])
        normalized_inventory.append(dict(row))
    if (
        normalized_inventory
        != sorted(normalized_inventory, key=lambda row: str(row["path"]))
        or normalized_inventory != authoritative_inventory
        or inventory_digest != _runtime_source_digest(authoritative_inventory)
    ):
        raise ReleaseGateError("active runtime source inventory is invalid")
    expected_overlay = _runtime_artifact_inventory(
        document["artifacts"],
        manifest_root=manifest_root,
        lock_rows=lock_rows,
    )
    _assert_active_local_project(
        local,
        manifest_root=manifest_root,
        source_root=source_root,
        inventory_digest=str(inventory_digest),
    )
    _assert_runtime_tree_payloads(
        source_root,
        expected_source,
        context="active runtime source",
        modes=source_modes,
    )
    _assert_runtime_tree_payloads(
        build_backend_root,
        expected_overlay,
        context="active runtime overlay",
    )
    controller_relative = "scripts/check_release_gate.py"
    if (
        source_modes.get(controller_relative) != "100644"
        or Path(sys.argv[0]).resolve(strict=True)
        != source_root / PurePosixPath(controller_relative)
    ):
        raise ReleaseGateError("active runtime controller binding is invalid")
    final_manifest_source = _secure_read_bytes(
        manifest_root,
        PurePosixPath("runtime-manifest.json"),
        context="active runtime manifest",
        max_bytes=64 * 1024 * 1024,
    )
    final_bound_lock = _secure_read_bytes(
        source_root,
        lock_relative,
        context="active runtime bound selected lock",
        max_bytes=8 * 1024 * 1024,
    )
    if (
        final_manifest_source != manifest_source
        or hashlib.sha256(final_manifest_source).hexdigest() != expected_digest
        or final_bound_lock != lock_source
        or _active_head_source_inventory(repository_root, head_oid)
        != authoritative_inventory
    ):
        raise ReleaseGateError("active runtime binding changed during validation")
    _runtime_artifact_inventory(
        document["artifacts"],
        manifest_root=manifest_root,
        lock_rows=lock_rows,
    )
    _assert_active_local_project(
        local,
        manifest_root=manifest_root,
        source_root=source_root,
        inventory_digest=str(inventory_digest),
    )
    _assert_runtime_tree_payloads(
        source_root,
        expected_source,
        context="active runtime source",
        modes=source_modes,
    )
    _assert_runtime_tree_payloads(
        build_backend_root,
        expected_overlay,
        context="active runtime overlay",
    )
    _assert_active_repository_snapshot(
        repository_root,
        commit_oid=head_oid,
        tree_oid=tree_oid,
    )
    return source_root, build_backend_root


def _active_runtime_paths(repository: Path) -> tuple[Path, Path] | None:
    names = (
        "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL",
        "HSCONFIG_RUNTIME_MANIFEST",
        "HSCONFIG_RUNTIME_MANIFEST_SHA256",
    )
    present = tuple(name in os.environ for name in names)
    if not any(present):
        return None
    if not all(present):
        raise ReleaseGateError("active runtime binding is incomplete")
    try:
        return _bound_active_runtime_paths(repository)
    except ReleaseGateError as exc:
        raise ReleaseGateError("active runtime binding is invalid") from exc
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise ReleaseGateError("active runtime binding is invalid") from exc


def _command_specs(
    root: Path,
    outputs: Path,
    tree_mode: TreeMode,
    *,
    owner_repository: Path | None = None,
) -> tuple[_CommandSpec, ...]:
    python = sys.executable
    active_runtime_paths = _active_runtime_paths(root)
    script_root = active_runtime_paths[0] if active_runtime_paths is not None else root
    script = script_root / "scripts" / "check_release_gate.py"
    build_inputs = root / "src" / "hsconfig" / "resources" / "audited_build_inputs.json"
    score_mode = "pre_cutover" if tree_mode != "final" else "final"
    owner_arguments = (
        ("--owner-repo", str(owner_repository))
        if owner_repository is not None
        else ()
    )
    common_internal = (
        python,
        str(script),
        "--repo",
        str(root),
        "--outputs",
        str(outputs),
        "--tree-mode",
        tree_mode,
        *owner_arguments,
        "--json",
        "--internal-check",
    )
    return (
        _CommandSpec("ruff", (python, "-m", "ruff", "check", "--no-cache", "src", "tests", "scripts"), 600),
        _CommandSpec("full_tests_and_coverage", (python, str(script_root / "scripts" / "run_coverage_gate.py")), 18_000),
        _CommandSpec(
            "contract_spine",
            (
                python,
                "-m",
                "hsconfig.cli",
                "contract-spine-sentinel",
                "--repo-root",
                str(root),
                "--json",
            ),
            600,
        ),
        _CommandSpec("twelve_deck_acceptance", (python, "-m", "pytest", "tests/test_audited_deck_set_acceptance.py", "-q", "-p", "no:cacheprovider"), 1_800),
        _CommandSpec("contract_mutations", (python, str(root / "scripts" / "run_contract_mutations.py"), "--json"), 1_200),
        _CommandSpec(
            "dependency_audit",
            (
                python,
                "-m",
                "pip_audit",
                "-r",
                str(root / "constraints-ci.txt"),
                "--strict",
                "--progress-spinner",
                "off",
            ),
            1_200,
        ),
        _CommandSpec("distribution", (python, str(root / "scripts" / "verify_distribution.py"), "--json"), 1_200),
        _CommandSpec("twelve_deck_determinism", (python, str(root / "scripts" / "verify_twelve_decks.py"), "--build-inputs", str(build_inputs), "--json"), 1_800),
        _CommandSpec("publishable_path_scan", (*common_internal, "publishable_path_scan"), 1_800),
        _CommandSpec("output_inventory", (python, str(root / "scripts" / "reconcile_outputs.py"), "--outputs", str(outputs), "--check", "--json"), 600),
        _CommandSpec("package_immutability", (python, "-m", "pytest", "tests/test_package_immutability_after_apply.py", "-q", "-p", "no:cacheprovider"), 900),
        _CommandSpec("transaction_fault_matrix", (python, "-m", "pytest", "tests/test_runtime_install_fault_matrix.py", "tests/test_output_publication_fault_matrix.py", "-q", "-p", "no:cacheprovider"), 1_800),
        _CommandSpec("repository_hygiene", (*common_internal, "repository_hygiene"), 300),
        _CommandSpec("version_consistency", (python, "-m", "pytest", "tests/test_version_contract.py", "-q", "-p", "no:cacheprovider"), 300),
        _CommandSpec(
            "near100_scorecard",
            (
                python,
                str(root / "scripts" / "check_near100_scorecard.py"),
                "--repo",
                str(root),
                "--outputs",
                str(outputs),
                "--mode",
                score_mode,
                "--evidence-stdin",
                "--json",
            ),
            600,
        ),
    )


def _canonical_module_text(source: bytes) -> str:
    try:
        text = source.decode("utf-8")
    except UnicodeError as exc:
        raise ReleaseGateError("release gate module is not bound to the requested repository") from exc
    if "\r" not in text:
        return text
    without_crlf = text.replace("\r\n", "")
    if "\r" in without_crlf or "\n" in without_crlf:
        raise ReleaseGateError("release gate module is not bound to the requested repository")
    return text.replace("\r\n", "\n")


def _verify_module_binding(repository: Path) -> None:
    try:
        for relative, loaded in (
            (PurePosixPath("src", "hsconfig", "release_gate.py"), Path(__file__)),
            (
                PurePosixPath("src", "hsconfig", "publishable_tree.py"),
                Path(publishable_tree_module.__file__ or ""),
            ),
        ):
            expected = repository.joinpath(*relative.parts)
            metadata = expected.lstat()
            repository_source = _secure_read_bytes(
                repository,
                relative,
                context="repository module binding",
            )
            loaded_source = _secure_read_bytes(
                loaded.parent,
                PurePosixPath(loaded.name),
                context="loaded module binding",
            )
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or _is_reparse(metadata)
                or _canonical_module_text(repository_source)
                != _canonical_module_text(loaded_source)
            ):
                raise ReleaseGateError(
                    "release gate module is not bound to the requested repository"
                )
    except OSError as exc:
        raise ReleaseGateError("release gate module binding cannot be verified") from exc


def _validate_pre_cutover_local_result(document: Mapping[str, Any]) -> None:
    expected_fields = {
        "schema_version",
        "version",
        "metrics",
        "open_p0_findings",
        "open_p1_findings",
        "overall_score",
        "passed",
    }
    if set(document) != expected_fields:
        raise ReleaseGateError("pre-cutover scorecard result schema mismatch")
    if (
        document.get("schema_version") != 1
        or document.get("version") != __version__
        or document.get("passed") is not False
    ):
        raise ReleaseGateError("pre-cutover scorecard identity/passed state mismatch")
    for finding in ("open_p0_findings", "open_p1_findings"):
        value = document.get(finding)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            raise ReleaseGateError("pre-cutover scorecard has open blocking findings")
    metrics = document.get("metrics")
    if not isinstance(metrics, list) or any(
        not isinstance(metric, Mapping) for metric in metrics
    ):
        raise ReleaseGateError("pre-cutover scorecard metrics schema mismatch")
    expected_metric_ids = (*HARD_METRIC_IDS, "overall_pre_run", "gameplay_quality")
    actual_metric_ids = tuple(metric.get("metric_id") for metric in metrics)
    if actual_metric_ids != expected_metric_ids:
        raise ReleaseGateError("pre-cutover scorecard metric set/order mismatch")
    for metric in metrics:
        metric_id = metric.get("metric_id")
        expected_status = (
            "pending_remote"
            if metric_id == "github_repository_polish"
            else "not_applicable"
            if metric_id == "gameplay_quality"
            else "pass"
        )
        if metric.get("status") != expected_status:
            raise ReleaseGateError(
                f"pre-cutover scorecard metric status mismatch: {metric_id}"
            )
    overall_score = document.get("overall_score")
    try:
        score = Decimal(overall_score) if isinstance(overall_score, str) else None
    except InvalidOperation as exc:
        raise ReleaseGateError("pre-cutover scorecard overall score is invalid") from exc
    if score is None or not score.is_finite() or score < Decimal("98"):
        raise ReleaseGateError("pre-cutover scorecard overall score is below minimum")


def _safe_detail(
    stdout: str,
    stderr: str,
    returncode: int,
    *,
    allow_pre_cutover_local: bool = False,
) -> dict[str, Any]:
    details: dict[str, Any] = {"returncode": returncode}
    stripped = stdout.strip()
    if stripped.startswith("[truncated sha256="):
        raise ReleaseGateError("subprocess stdout exceeded bounded capture")
    if stripped:
        try:
            parsed = _load_json_bytes(stripped.encode("utf-8"), source="subprocess stdout")
        except ReleaseGateError:
            if stripped.startswith(("{", "[")):
                raise
            details["stdout_sha256"] = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
        else:
            if allow_pre_cutover_local:
                if returncode != 0 or not isinstance(parsed, Mapping):
                    raise ReleaseGateError(
                        "pre-cutover scorecard must be a successful JSON subprocess"
                    )
                _validate_pre_cutover_local_result(parsed)
            elif isinstance(parsed, Mapping) and "passed" in parsed:
                reported = parsed["passed"]
                if not isinstance(reported, bool) or reported is not (returncode == 0):
                    raise ReleaseGateError(
                        "subprocess JSON passed value contradicts process return code"
                    )
            if isinstance(parsed, Mapping) and "returncode" in parsed:
                nested_returncode = parsed.get("returncode")
                if (
                    isinstance(nested_returncode, bool)
                    or not isinstance(nested_returncode, int)
                    or nested_returncode != returncode
                ):
                    raise ReleaseGateError(
                        "subprocess JSON returncode contradicts process return code"
                    )
            details["result"] = _portable_value(parsed)
    if stderr.strip():
        details["stderr_sha256"] = hashlib.sha256(stderr.encode("utf-8")).hexdigest()
    return details


def _controlled_environment(repository: Path) -> dict[str, str]:
    active_runtime_paths = _active_runtime_paths(repository)
    environment = _base_environment()
    for key in tuple(environment):
        upper = key.upper()
        if upper.startswith(("COVERAGE_", "HYPOTHESIS_", "PYTHON", "PYTEST_")) or upper in {
            "VIRTUAL_ENV",
            "CONDA_PREFIX",
        }:
            environment.pop(key, None)
        elif upper.startswith("PIP_"):
            environment.pop(key, None)
    environment.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": (
                os.pathsep.join(str(path) for path in active_runtime_paths)
                if active_runtime_paths is not None
                else str(repository / "src")
            ),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTEST_PLUGINS": "pytest_cov.plugin,_hypothesis_pytestplugin",
        }
    )
    return environment


def _distribution_build_environment(repository: Path) -> dict[str, str]:
    active_runtime_paths = _active_runtime_paths(repository)
    environment = _controlled_environment(repository)
    for name in (
        "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL",
        "HSCONFIG_RUNTIME_MANIFEST",
        "HSCONFIG_RUNTIME_MANIFEST_SHA256",
    ):
        environment.pop(name, None)
    if active_runtime_paths is None:
        environment.pop("PYTHONPATH", None)
    else:
        environment["PYTHONPATH"] = str(active_runtime_paths[1])
    return environment


class _BoundedCapture:
    def __init__(self, limit: int = 64 * 1024) -> None:
        self._limit = limit
        self._tail = bytearray()
        self._digest = hashlib.sha256()
        self.total = 0

    def drain(self, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                self.total += len(chunk)
                self._digest.update(chunk)
                self._tail.extend(chunk)
                if len(self._tail) > self._limit:
                    del self._tail[: len(self._tail) - self._limit]
        except (OSError, ValueError):
            return

    def text(self) -> str:
        decoded = bytes(self._tail).decode("utf-8", errors="replace")
        if self.total > self._limit:
            return f"[truncated sha256={self._digest.hexdigest()}]\n{decoded}"
        return decoded


_GATED_LAUNCHER = (
    "import json,os,subprocess,sys; header=bytearray(); "
    "[(header.extend(chunk),None)[1] for chunk in iter(lambda:os.read(0,1),b'\\n')]; "
    "argv=json.loads(header); "
    "assert isinstance(argv,list) and argv and all(isinstance(x,str) for x in argv); "
    "raise SystemExit(subprocess.run(argv,stdin=sys.stdin.buffer).returncode)"
)


def _linux_direct_children() -> set[int]:
    if sys.platform != "linux":
        return set()
    children: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="ascii").split()
            if len(fields) > 4 and int(fields[3]) == os.getpid():
                children.add(int(entry.name))
        except (OSError, UnicodeError, ValueError):
            continue
    return children


class _ProcessTreeLease:
    def __init__(self, process: subprocess.Popen[bytes], baseline: set[int]) -> None:
        self.process = process
        self.baseline = baseline
        self.job_handle: int | None = None
        if os.name == "nt":
            self._assign_windows_job()

    def _assign_windows_job(self) -> None:
        import ctypes
        from ctypes import wintypes

        class BasicLimitInformation(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class ExtendedLimitInformation(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimitInformation),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        job = kernel32.CreateJobObjectW(None, None)
        information = ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = 0x00002000
        if (
            not job
            or not kernel32.SetInformationJobObject(
                job, 9, ctypes.byref(information), ctypes.sizeof(information)
            )
            or not kernel32.AssignProcessToJobObject(
                job, wintypes.HANDLE(int(self.process._handle))  # noqa: SLF001
            )
        ):
            if job:
                kernel32.CloseHandle(job)
            raise OSError("subprocess job assignment failed")
        self.job_handle = int(job)

    def terminate_remaining(self) -> None:
        if os.name == "nt":
            if self.job_handle is not None:
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
                kernel32.CloseHandle.restype = wintypes.BOOL
                kernel32.CloseHandle(wintypes.HANDLE(self.job_handle))
                self.job_handle = None
            elif self.process.poll() is None:
                self.process.kill()
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            if sys.platform == "linux":
                for _ in range(4):
                    escaped = _linux_direct_children() - self.baseline
                    if not escaped:
                        break
                    for pid in escaped:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    for pid in escaped:
                        try:
                            os.waitpid(pid, 0)
                        except ChildProcessError:
                            pass
        if self.process.poll() is None:
            self.process.kill()
        try:
            self.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=30)


def _enable_posix_subreaper() -> None:
    if sys.platform != "linux":
        return
    import ctypes

    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise OSError("subprocess subreaper setup failed")


def _execute_bounded(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    stdin_data: bytes | None = None,
) -> subprocess.CompletedProcess[str]:
    # Every subprocess receives a unique, disposable tool-state root outside
    # the checkout. This prevents an earlier pytest/Hypothesis/coverage command
    # from poisoning a later repository-hygiene check and cleans the state on
    # both success and exception paths.
    with TemporaryDirectory(prefix="hsconfig-release-gate-tool-") as temporary:
        isolation_root = Path(temporary).resolve()
        checkout = cwd.resolve()
        if isolation_root == checkout or checkout in isolation_root.parents:
            raise ReleaseGateError("subprocess tool-state root is inside the checkout")
        tool_directories = {
            name: isolation_root / name
            for name in (
                "cache",
                "hypothesis",
                "pip-cache",
                "pycache",
                "pytest-cache",
                "pytest-temp",
            )
        }
        for directory in tool_directories.values():
            directory.mkdir(mode=0o700)
        isolated_environment = dict(env)
        isolated_environment.update(
            {
                "COVERAGE_FILE": str(isolation_root / ".coverage"),
                "HYPOTHESIS_STORAGE_DIRECTORY": str(tool_directories["hypothesis"]),
                "PIP_CACHE_DIR": str(tool_directories["pip-cache"]),
                "PYTEST_DEBUG_TEMPROOT": str(tool_directories["pytest-temp"]),
                "PYTHONPYCACHEPREFIX": str(tool_directories["pycache"]),
                "TMP": str(isolation_root),
                "TEMP": str(isolation_root),
                "TMPDIR": str(isolation_root),
                "TOX_ENV_DIR": str(tool_directories["pytest-cache"]),
                "XDG_CACHE_HOME": str(tool_directories["cache"]),
            }
        )
        coverage_report = (
            cwd / "coverage.json"
            if any(Path(argument).name == "run_coverage_gate.py" for argument in command)
            else None
        )
        if coverage_report is not None and (
            coverage_report.exists() or coverage_report.is_symlink()
        ):
            raise ReleaseGateError("coverage report residue exists before execution")
        try:
            return _execute_bounded_process(
                command,
                cwd=cwd,
                env=isolated_environment,
                timeout=timeout,
                stdin_data=stdin_data,
            )
        finally:
            if coverage_report is not None and (
                coverage_report.exists() or coverage_report.is_symlink()
            ):
                metadata = coverage_report.lstat()
                if (
                    not stat.S_ISREG(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                    or _is_reparse(metadata)
                    or getattr(metadata, "st_nlink", 1) not in {0, 1}
                ):
                    raise ReleaseGateError("coverage report cleanup found unsafe residue")
                coverage_report.unlink()


def _execute_bounded_process(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    stdin_data: bytes | None = None,
) -> subprocess.CompletedProcess[str]:
    platform_options: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    stdout_capture: _BoundedCapture | None = None
    stderr_capture: _BoundedCapture | None = None
    capture_threads: tuple[threading.Thread, ...] = ()
    started_capture_threads: list[threading.Thread] = []
    writer_errors: list[BaseException] = []
    writer: threading.Thread | None = None
    writer_started = False
    process: subprocess.Popen[bytes] | None = None
    lease: _ProcessTreeLease | None = None
    returncode = 2
    if os.name != "nt":
        _enable_posix_subreaper()
    baseline = _linux_direct_children()
    try:
        process = subprocess.Popen(
            (
                _process_tree_gate_interpreter(sys.executable),
                "-I",
                "-S",
                "-B",
                "-c",
                _GATED_LAUNCHER,
            ),
            cwd=cwd,
            env=dict(env),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            **platform_options,
        )
        lease = _ProcessTreeLease(process, baseline)
        stdout_capture = _BoundedCapture()
        stderr_capture = _BoundedCapture()
        capture_threads = (
            threading.Thread(target=stdout_capture.drain, args=(process.stdout,), daemon=True),
            threading.Thread(target=stderr_capture.drain, args=(process.stderr,), daemon=True),
        )

        launch_payload = (
            json.dumps(list(command), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            + b"\n"
            + (stdin_data or b"")
        )

        def write_stdin() -> None:
            if process is None or process.stdin is None:
                return
            try:
                process.stdin.write(launch_payload)
                process.stdin.flush()
            except BrokenPipeError:
                pass
            except BaseException as exc:
                writer_errors.append(exc)
            finally:
                process.stdin.close()

        writer = threading.Thread(target=write_stdin, daemon=True)
        if process.stdout is None or process.stderr is None:
            raise OSError("subprocess pipes unavailable")
        for thread in capture_threads:
            try:
                thread.start()
            except BaseException:
                if thread.is_alive():
                    started_capture_threads.append(thread)
                raise
            started_capture_threads.append(thread)
        try:
            writer.start()
        except BaseException:
            writer_started = writer.is_alive()
            raise
        writer_started = True
        returncode = process.wait(timeout=timeout)
        lease.terminate_remaining()
    except BaseException:
        try:
            if lease is not None:
                lease.terminate_remaining()
            elif process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=30)
        except BaseException:
            pass
        raise
    finally:
        deadline = time.monotonic() + 30.0
        joiners = ([writer] if writer is not None and writer_started else []) + started_capture_threads
        for thread in joiners:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        alive = [thread for thread in joiners if thread.is_alive()]
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        pass
        if alive:
            raise OSError("subprocess transport did not terminate before hard deadline")
    if writer_errors:
        raise OSError("subprocess stdin transport failed") from writer_errors[0]
    if stdout_capture is None or stderr_capture is None:
        raise OSError("subprocess capture unavailable")
    return subprocess.CompletedProcess(
        command,
        returncode,
        stdout=stdout_capture.text(),
        stderr=stderr_capture.text(),
    )


def _run_one(
    spec: _CommandSpec,
    *,
    repository: Path,
    stdin_data: bytes | None = None,
) -> ReleaseCheck:
    print(f"[release-gate] {spec.name}", file=sys.stderr, flush=True)
    environment = _controlled_environment(repository)
    try:
        if spec.name == "dependency_audit":
            _validate_selected_audit_projection(repository)
        effective_stdin = stdin_data
        if any(
            Path(argument).name == "check_release_gate.py" for argument in spec.command
        ) and "--internal-check" in spec.command:
            sentinel = environment.get("HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL", "")
            if re.fullmatch(r"[0-9a-f]{64}", sentinel) is None:
                raise ReleaseGateError("internal release check channel is unavailable")
            effective_stdin = sentinel.encode("ascii") + b"\n"
        completed = _execute_bounded(
            spec.command,
            cwd=repository,
            env=environment,
            timeout=spec.timeout,
            stdin_data=effective_stdin,
        )
    except subprocess.TimeoutExpired:
        return ReleaseCheck(
            name=spec.name,
            passed=False,
            command=spec.command,
            details={"returncode": None, "error": "timeout", "timeout_seconds": spec.timeout},
        )
    except Exception as exc:
        return ReleaseCheck(
            name=spec.name,
            passed=False,
            command=spec.command,
            details={"returncode": None, "error": f"execution_failed:{type(exc).__name__}"},
        )
    try:
        mode_positions = [
            index for index, argument in enumerate(spec.command) if argument == "--mode"
        ]
        pre_cutover_near100 = (
            spec.name == "near100_scorecard"
            and len(mode_positions) == 1
            and mode_positions[0] + 1 < len(spec.command)
            and spec.command[mode_positions[0] + 1] == "pre_cutover"
            and any(
                Path(argument).name == "check_near100_scorecard.py"
                for argument in spec.command
            )
            and "--evidence-stdin" in spec.command
        )
        details = _safe_detail(
            completed.stdout,
            completed.stderr,
            completed.returncode,
            allow_pre_cutover_local=pre_cutover_near100,
        )
    except ReleaseGateError as exc:
        return ReleaseCheck(
            name=spec.name,
            passed=False,
            command=spec.command,
            details={"returncode": completed.returncode, "error": _redact_text(str(exc))},
        )
    return ReleaseCheck(
        name=spec.name,
        passed=completed.returncode == 0,
        command=spec.command,
        details=details,
    )


def _validate_selected_audit_projection(repository: Path) -> None:
    minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    lock_path = repository / f"pylock.{minor}.toml"
    constraints_path = repository / "constraints-ci.txt"
    try:
        lock_document = tomllib.loads(
            _secure_read_bytes(
                repository,
                PurePosixPath(lock_path.name),
                context="selected audit lock",
            ).decode("utf-8")
        )
        constraints_source = _secure_read_bytes(
            repository,
            PurePosixPath(constraints_path.name),
            context="selected audit projection",
        ).decode("utf-8")
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ReleaseGateError("selected audit graph cannot be parsed") from exc
    packages = lock_document.get("packages")
    if not isinstance(packages, list) or len(packages) != 43:
        raise ReleaseGateError("selected audit lock must contain exactly 43 packages")
    locked: dict[str, str] = {}
    for row in packages:
        if not isinstance(row, Mapping):
            raise ReleaseGateError("selected audit lock package row is invalid")
        name = row.get("name")
        version = row.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise ReleaseGateError("selected audit lock package row is invalid")
        identity = re.sub(r"[-_.]+", "-", name).casefold()
        if identity in locked:
            raise ReleaseGateError("selected audit lock contains duplicate package")
        locked[identity] = version
    projected: dict[str, str] = {}
    for raw_line in constraints_source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)", line)
        if match is None:
            raise ReleaseGateError("selected audit projection row is invalid")
        identity = re.sub(r"[-_.]+", "-", match.group(1)).casefold()
        if identity in projected:
            raise ReleaseGateError("selected audit projection contains duplicate package")
        projected[identity] = match.group(2)
    if projected != locked:
        raise ReleaseGateError("selected audit projection differs from selected lock")


def _repository_identity(root: Path) -> str:
    remote = str(_git(root, "remote", "get-url", "origin")).strip().replace("\\", "/")
    if remote.startswith("git@github.com:"):
        remote = remote.removeprefix("git@github.com:")
    elif "github.com/" in remote:
        remote = remote.split("github.com/", 1)[1]
    identity = remote.removesuffix(".git").strip("/")
    if identity.count("/") != 1:
        raise ReleaseGateError("repository identity cannot be derived from origin")
    return identity


def _dirty_tree_fingerprint(root: Path) -> tuple[str, str]:
    status = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", text=False)
    diff = _git(root, "diff", "--binary", "HEAD", "--", text=False)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z", text=False)
    if not all(isinstance(value, bytes) for value in (status, diff, untracked)):
        raise ReleaseGateError("binary repository inspection returned text")
    digest = hashlib.sha256()
    digest.update(b"status\0" + status)
    digest.update(b"diff\0" + diff)
    for encoded in sorted(value for value in untracked.split(b"\0") if value):
        try:
            relative = encoded.decode("utf-8")
        except UnicodeError as exc:
            raise ReleaseGateError("untracked path is not UTF-8") from exc
        pure = PurePosixPath(relative)
        if pure.is_absolute() or "\\" in relative or any(
            part in {"", ".", ".."} for part in pure.parts
        ):
            raise ReleaseGateError("untracked path is non-canonical")
        path = root
        for index, part in enumerate(pure.parts):
            path /= part
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise ReleaseGateError("untracked path cannot be inspected") from exc
            final = index == len(pure.parts) - 1
            expected = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
            if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise ReleaseGateError("untracked path contains link/reparse/non-regular data")
            if final and getattr(metadata, "st_nlink", 1) not in {0, 1}:
                raise ReleaseGateError("untracked file must not be a hardlink")
        digest.update(
            b"untracked\0"
            + encoded
            + b"\0"
            + _secure_read_bytes(
                root,
                PurePosixPath(relative),
                context="untracked fingerprint source",
            )
        )
    return ("dirty" if status else "clean", digest.hexdigest())


def _owner_repository_snapshot(owner_repository: Path) -> tuple[str, ...]:
    state, fingerprint = _dirty_tree_fingerprint(owner_repository)
    if state != "clean":
        raise ReleaseGateError("candidate owner repository must remain clean")
    return (
        str(_git(owner_repository, "rev-parse", "HEAD")).strip(),
        str(_git(owner_repository, "rev-parse", "HEAD^{tree}")).strip(),
        fingerprint,
        _repository_identity(owner_repository),
        _canonical_origin(owner_repository),
    )


def _capture_snapshot(
    repository: Path,
    outputs_root: Path,
    *,
    owner_repository: Path | None = None,
) -> _GateSnapshot:
    outputs_digest = _outputs_inventory_sha256(repository, outputs_root)
    state, fingerprint = _dirty_tree_fingerprint(repository)
    if state != "clean":
        raise ReleaseGateError("release gate refuses a dirty repository")
    return _GateSnapshot(
        commit_oid=str(_git(repository, "rev-parse", "HEAD")).strip(),
        tree_oid=str(_git(repository, "rev-parse", "HEAD^{tree}")).strip(),
        repository_fingerprint=fingerprint,
        outputs_inventory_sha256=outputs_digest,
        repository_identity=_repository_identity(repository),
        repository_path_identity=_directory_path_identity(
            repository,
            context="repository root",
        ),
        outputs_path_identity=_directory_path_identity(
            outputs_root,
            context="outputs root",
        ),
        owner_repository_snapshot=(
            _owner_repository_snapshot(owner_repository)
            if owner_repository is not None
            else None
        ),
        owner_path_identity=(
            _directory_path_identity(
                owner_repository,
                context="candidate owner repository",
            )
            if owner_repository is not None
            else None
        ),
    )


def _assert_snapshot_unchanged(
    repository: Path,
    outputs_root: Path,
    expected: _GateSnapshot,
    *,
    owner_repository: Path | None = None,
) -> None:
    try:
        actual = _capture_snapshot(
            repository,
            outputs_root,
            owner_repository=owner_repository,
        )
    except ReleaseGateError as exc:
        if owner_repository is not None:
            raise ReleaseGateError(
                "candidate owner, repository, or outputs changed during release gate"
            ) from exc
        raise ReleaseGateError("repository or outputs changed during release gate") from exc
    if actual != expected:
        if owner_repository is not None:
            raise ReleaseGateError(
                "candidate owner, repository, or outputs changed during release gate"
            )
        raise ReleaseGateError("repository or outputs changed during release gate")


def _atomic_release_check(check_id: str) -> str:
    mappings = {
        "contract_spine": "contract_spine",
        "twelve_deck_acceptance": "twelve_deck_acceptance",
        "version_consistency": "version_consistency",
        "owner_policy": "contract_spine",
        "runtime_surface_policy": "contract_spine",
        "lowering_precision": "contract_spine",
        "lowering_recall": "contract_spine",
        "branch_coverage": "full_tests_and_coverage",
        "critical_coverage": "full_tests_and_coverage",
        "contract_mutations": "contract_mutations",
        "determinism": "twelve_deck_determinism",
        "distribution": "distribution",
        "deck_identity": "twelve_deck_acceptance",
        "main_slots": "twelve_deck_acceptance",
        "card_module_dispositions": "contract_spine",
        "claim_dispositions": "contract_spine",
        "globalvalues_dispositions": "contract_spine",
        "architecture_tests": "contract_spine",
        "transaction_fault_matrix": "transaction_fault_matrix",
        "package_immutability": "package_immutability",
        "distribution_contents": "distribution",
        "publishable_path_scan": "publishable_path_scan",
        "output_inventory": "output_inventory",
        "repository_hygiene": "repository_hygiene",
        "workspace_residue": "repository_hygiene",
    }
    try:
        return mappings[check_id]
    except KeyError as exc:
        raise ReleaseGateError(f"no release check owns atomic evidence: {check_id}") from exc


_FINAL_DISPOSITIONS = frozenset(
    {
        "runtime_emitted",
        "bot_delegated",
        "suppressed_unsupported_surface",
        "suppressed_insufficient_authority",
        "analysis_only_sideboard",
    }
)
_LEDGER_FIELDS = frozenset(
    {
        "schema_version",
        "deck_fingerprint",
        "content_sha256",
        "authority",
        "normal_apply_authority",
        "apply_blocking",
        "operator_gate_impact",
        "cards",
        "claims",
    }
)
_LEDGER_CARD_FIELDS = frozenset(
    {
        "composite_card_key",
        "deck_fingerprint",
        "zone",
        "physical_owner",
        "official_semantics",
        "claim_ids",
        "authority_lane",
        "disposition",
        "reason_code",
        "runtime_paths",
        "evidence_ids",
    }
)
_LEDGER_CLAIM_FIELDS = frozenset(
    {
        "composite_claim_identity",
        "deck_fingerprint",
        "claim_id",
        "claim_kind",
        "disposition",
        "reason_code",
        "runtime_paths",
        "evidence_id",
    }
)
_AUDIT_FIELDS = frozenset(
    {
        "schema_version",
        "deck_name",
        "authority",
        "normal_apply_authority",
        "apply_blocking",
        "operator_gate_impact",
        "summary",
        "card_rows",
        "claim_rows",
        "claim_lifecycle_rows",
    }
)
_AUDIT_CLAIM_FIELDS = frozenset(
    {
        "claim_id",
        "claim_kind",
        "cards",
        "evidence_text_short",
        "source_title",
        "source_type",
        "source_lane",
        "policy_lane",
        "claim_readiness",
        "evidence_authority",
        "evidence_lane_error",
        "strategic_receipt_verified",
        "trust_ceiling",
        "lane",
        "first_reason",
        "lowered_surfaces",
        "surfaces",
    }
)
_AUDIT_CLAIM_FIELD_VARIANTS = frozenset(
    {
        _AUDIT_CLAIM_FIELDS,
        _AUDIT_CLAIM_FIELDS | {"action", "condition", "selector"},
        _AUDIT_CLAIM_FIELDS | {"operator", "timing_kind"},
    }
)
_AUDIT_SUMMARY_FIELDS = frozenset(
    {
        "cards_total",
        "cards_with_missing_links",
        "cards_with_runtime_lowered_claims",
        "cards_with_suppressed_claims",
        "claim_kind_policy_counts",
        "claim_lifecycle_decision_counts",
        "claims_total",
        "report_only_claims",
        "runtime_evidence_required_claims",
        "runtime_lowered_claims",
        "suppressed_claims",
        "unsupported_or_unmapped_claims",
    }
)
_AUDIT_CARD_FIELDS = frozenset(
    {
        "card_id",
        "claim_lanes",
        "deck_zone",
        "first_missing_link",
        "name",
        "readiness_lane",
        "roles",
        "runtime_eligible",
        "runtime_surfaces",
        "sideboard_memberships",
        "sideboard_owner_card_id",
        "sideboard_owner_card_ids",
    }
)
_AUDIT_LIFECYCLE_FIELDS = frozenset(
    {
        "builder_or_router_decision",
        "claim_id",
        "claim_kind",
        "emitted_files",
        "final_runtime_effect",
        "first_missing_link",
        "operator_impact",
        "policy_lane",
        "quarantine_reason",
        "quarantine_status",
        "runtime_eligibility",
        "runtime_surface",
        "suppressed_reason",
        "surface_gate_decision",
        "surface_gate_reason",
    }
)
_AUDIT_SURFACE_FIELDS = frozenset({"allowed", "claim_kind", "reason", "surface"})
_AUDIT_SIDEBOARD_MEMBERSHIP_FIELDS = frozenset(
    {"count", "owner_card_id", "sideboard_index"}
)
_AUDIT_EVIDENCE_AUTHORITY_FIELDS = frozenset(
    {
        "as_of_date",
        "authority_id",
        "claim_kind",
        "content_sha256",
        "exact_deck_fingerprint",
        "lane",
        "reason",
        "runtime_authorized",
        "source_identity",
    }
)
_CLAIM_KINDS = frozenset(
    {
        "card_role",
        "choose_one_choice",
        "combo_sequence",
        "discover_choice",
        "gameplan_posture",
        "hero_power_transform",
        "known_bad_pattern",
        "mechanic_usage",
        "mulligan_keep",
        "targeting_rule",
    }
)
_FIRST_REASONS = frozenset(
    {
        "attack_owner_not_proven",
        "battlecry_owner_does_not_attack",
        "buff_target_owner_mismatch",
        "choose_one_condition_not_encoded",
        "claim_kind_not_mulligan_surface",
        "claim_not_runtime_lowerable",
        "combo_count_condition_not_encoded",
        "discard_trigger_not_manual_play",
        "discover_condition_not_encoded",
        "dredge_condition_not_encoded",
        "globalvalues_requires_exact_deck_match",
        "hand_position_condition_not_encoded",
        "health_cost_condition_not_encoded",
        "imbue_condition_not_encoded",
        "mulligan_requires_exact_deck_match",
        "outcast_condition_not_encoded",
        "reciprocal_burn_report_only",
        "semantic_surface_not_expressible",
        "semantic_surface_not_proven",
        "shatter_state_not_encoded",
        "spell_cannot_own_on_board",
        "spell_cannot_use_battlecry_target",
        "strategic_provenance_not_live_verified",
        "symmetric_board_condition_not_encoded",
        "symmetric_summon_condition_not_encoded",
        "trigger_owner_does_not_attack",
        "unresolved_option_identity",
        "variable_cost_condition_not_encoded",
    }
)
_SURFACE_REASONS = frozenset(
    {
        "allowed",
        "claim_kind_not_cardid_surface",
        "claim_kind_not_combo_surface",
        "claim_kind_not_globalvalues_surface",
        "claim_kind_not_mulligan_surface",
        "claim_not_runtime_lowerable",
        "combo_requires_public_guide_source",
        "globalvalues_requires_exact_deck_match",
        "mulligan_requires_exact_deck_match",
        "strategic_provenance_not_live_verified",
        "targeting_requires_exact_deck_match",
        "targeting_requires_public_guide_source",
    }
)
_SURFACE_GATE_REASONS = frozenset(
    {
        "allowed",
        "bot_delegated",
        "claim_kind_not_mulligan_surface",
        "claim_not_runtime_lowerable",
        "globalvalues_requires_exact_deck_match",
        "mulligan_requires_exact_deck_match",
        "strategic_provenance_not_live_verified",
        "targeting_requires_public_guide_source",
    }
)
_CARD_FIRST_MISSING_LINKS = frozenset(
    {
        "needs_condition_lowering",
        "needs_runtime_surface",
        "needs_target_scope",
        "none",
        "semantic_surface_not_expressible",
    }
)
_LIFECYCLE_SUPPRESSED_REASONS = _FIRST_REASONS | frozenset(
    {"bot_delegated", "builder_or_router_missing", "source_eligibility"}
)


def _require_closed_fields(
    value: Any,
    fields: frozenset[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ReleaseGateError(f"{label} schema mismatch")
    return value


def _require_closed_audit_claim(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or frozenset(value) not in _AUDIT_CLAIM_FIELD_VARIANTS:
        raise ReleaseGateError("semantic source audit claim row schema mismatch")
    return value


def _string_sequence(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and all(isinstance(item, str) for item in value)
    )


def _string_in(value: Any, choices: frozenset[str] | set[str]) -> bool:
    return isinstance(value, str) and value in choices


def _validate_audit_claim_nested(row: Mapping[str, Any]) -> None:
    surfaces = row.get("surfaces")
    if not isinstance(surfaces, Mapping) or set(surfaces) != {
        "cardid",
        "combo",
        "globalvalues",
        "mulligan",
    }:
        raise ReleaseGateError("semantic source audit claim surfaces schema mismatch")
    for surface_name, raw in surfaces.items():
        surface = _require_closed_fields(
            raw, _AUDIT_SURFACE_FIELDS, label="semantic source audit surface"
        )
        if (
            not isinstance(surface.get("allowed"), bool)
            or surface.get("claim_kind") != row.get("claim_kind")
            or surface.get("surface") != surface_name
            or not _string_in(surface.get("reason"), _SURFACE_REASONS)
            or surface.get("allowed") is not (surface.get("reason") == "allowed")
        ):
            raise ReleaseGateError("semantic source audit surface binding mismatch")
    for field in ("cards", "lowered_surfaces"):
        if not _string_sequence(row.get(field)):
            raise ReleaseGateError("semantic source audit claim row schema mismatch")
    if row.get("action") is not None and not isinstance(row.get("action"), str):
        raise ReleaseGateError("semantic source audit claim row schema mismatch")
    if row.get("selector") is not None and not isinstance(row.get("selector"), str):
        raise ReleaseGateError("semantic source audit claim row schema mismatch")
    condition = row.get("condition")
    if condition is not None and not (
        isinstance(condition, str) or (isinstance(condition, Mapping) and not condition)
    ):
        raise ReleaseGateError("semantic source audit claim row schema mismatch")
    if (
        not _string_in(row.get("claim_kind"), _CLAIM_KINDS)
        or not _string_in(row.get("source_type"), {"", "official_card_data", "public_guide"})
        or not _string_in(
            row.get("source_lane"),
            {"", "archetype_matched_public_guide", "deck_matched_public_guide"},
        )
        or not _string_in(
            row.get("policy_lane"), {"runtime_lowerable", "suppressed_or_conditional"}
        )
        or not _string_in(
            row.get("claim_readiness"),
            {
            "explicit_low_confidence",
            "guide_backed",
            "source_backed_static_semantics",
            },
        )
        or not (
            row.get("evidence_lane_error") is None
            or row.get("evidence_lane_error") == "evidence_lane_unclassified"
        )
        or not isinstance(row.get("strategic_receipt_verified"), bool)
        or not _string_in(
            row.get("trust_ceiling"), {"guide", "report_only", "static_semantics"}
        )
        or not _string_in(
            row.get("lane"),
            {
            "report_only",
            "runtime_lowered",
            "suppressed_with_reason",
            "unsupported_or_unmapped",
            },
        )
        or not _string_in(row.get("first_reason"), _FIRST_REASONS)
        or not isinstance(row.get("evidence_text_short"), str)
        or not isinstance(row.get("source_title"), str)
        or ("action" in row and row.get("action") != "hold")
        or ("operator" in row and row.get("operator") != ">>")
        or ("timing_kind" in row and row.get("timing_kind") != "same_turn")
    ):
        raise ReleaseGateError("semantic source audit claim row scalar domain mismatch")


def _validate_evidence_authority(
    row: Mapping[str, Any], deck_fingerprint: str
) -> Mapping[str, Any] | None:
    raw = row.get("evidence_authority")
    if raw is None:
        if row.get("evidence_lane_error") != "evidence_lane_unclassified":
            raise ReleaseGateError("semantic source authority evidence binding mismatch")
        return None
    authority = _require_closed_fields(
        raw,
        _AUDIT_EVIDENCE_AUTHORITY_FIELDS,
        label="semantic source authority evidence",
    )
    strings = (
        "as_of_date",
        "authority_id",
        "claim_kind",
        "content_sha256",
        "reason",
        "source_identity",
    )
    if (
        any(not isinstance(authority.get(field), str) or not authority[field] for field in strings)
        or authority.get("claim_kind") != row.get("claim_kind")
        or row.get("evidence_lane_error") is not None
        or re.fullmatch(r"sha256:[0-9a-f]{64}", authority["content_sha256"]) is None
    ):
        raise ReleaseGateError("semantic source authority evidence binding mismatch")
    lane = authority.get("lane")
    if lane == "C":
        valid_lane = (
            authority.get("runtime_authorized") is False
            and authority.get("exact_deck_fingerprint") is None
            and re.fullmatch(r"C:claim_[0-9a-f]{12}", authority["authority_id"])
            is not None
        )
    elif lane == "B":
        valid_lane = (
            authority.get("runtime_authorized") is True
            and authority.get("exact_deck_fingerprint") == deck_fingerprint
            and row.get("strategic_receipt_verified") is True
            and re.fullmatch(r"B:claim_[0-9a-f]{12}", authority["authority_id"])
            is not None
        )
    else:
        valid_lane = False
    if not valid_lane:
        raise ReleaseGateError("semantic source authority evidence binding mismatch")
    return authority


def _validate_source_audit(
    audit: Mapping[str, Any],
    ledger_cards: Sequence[Any],
    ledger_claims: Sequence[Any],
) -> dict[str, Mapping[str, Any]]:
    summary = _require_closed_fields(
        audit.get("summary"), _AUDIT_SUMMARY_FIELDS, label="semantic source audit summary"
    )
    card_rows = audit.get("card_rows")
    claim_rows = audit.get("claim_rows")
    lifecycle_rows = audit.get("claim_lifecycle_rows")
    if (
        not isinstance(card_rows, Mapping)
        or not isinstance(claim_rows, Mapping)
        or not isinstance(lifecycle_rows, Sequence)
        or isinstance(lifecycle_rows, (str, bytes, bytearray))
        or len(card_rows) != len(ledger_cards)
        or len(claim_rows) != len(ledger_claims)
        or len(lifecycle_rows) != len(ledger_claims)
    ):
        raise ReleaseGateError("semantic source audit row count mismatch")

    for key, raw in card_rows.items():
        row = _require_closed_fields(
            raw, _AUDIT_CARD_FIELDS, label="semantic source audit card row"
        )
        claim_lanes = row.get("claim_lanes")
        if (
            not isinstance(key, str)
            or row.get("card_id") != key
            or not isinstance(claim_lanes, Mapping)
            or any(
                lane not in {"runtime_lowered", "suppressed_with_reason", "unsupported_or_unmapped"}
                or not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
                for lane, count in claim_lanes.items()
            )
            or not isinstance(row.get("runtime_eligible"), bool)
            or any(
                not _string_sequence(row.get(field))
                for field in ("roles", "runtime_surfaces", "sideboard_owner_card_ids")
            )
            or any(
                not isinstance(row.get(field), str)
                for field in ("deck_zone", "first_missing_link", "name", "readiness_lane")
            )
            or not _string_in(row.get("deck_zone"), {"main", "sideboard"})
            or not _string_in(row.get("first_missing_link"), _CARD_FIRST_MISSING_LINKS)
            or not _string_in(
                row.get("readiness_lane"),
                {"linked_runtime_source", "report_only_supported", "runtime_emitted"},
            )
            or not row.get("name")
            or not (
                row.get("sideboard_owner_card_id") is None
                or isinstance(row.get("sideboard_owner_card_id"), str)
            )
        ):
            raise ReleaseGateError("semantic source audit card row binding mismatch")
        memberships = row.get("sideboard_memberships")
        if (
            not isinstance(memberships, Sequence)
            or isinstance(memberships, (str, bytes, bytearray))
            or any(
                set(membership) != _AUDIT_SIDEBOARD_MEMBERSHIP_FIELDS
                or not isinstance(membership.get("owner_card_id"), str)
                or not isinstance(membership.get("count"), int)
                or isinstance(membership.get("count"), bool)
                or membership["count"] <= 0
                or not isinstance(membership.get("sideboard_index"), int)
                or isinstance(membership.get("sideboard_index"), bool)
                or membership["sideboard_index"] < 0
                for membership in memberships
                if isinstance(membership, Mapping)
            )
            or any(not isinstance(membership, Mapping) for membership in memberships)
        ):
            raise ReleaseGateError("semantic source audit card row binding mismatch")

    claims_by_id: dict[str, Mapping[str, Any]] = {}
    for key, raw in claim_rows.items():
        row = _require_closed_audit_claim(raw)
        _validate_audit_claim_nested(row)
        if not isinstance(key, str) or row.get("claim_id") != key or key in claims_by_id:
            raise ReleaseGateError("semantic source audit claim identity mismatch")
        claims_by_id[key] = row

    lifecycle_by_id: dict[str, Mapping[str, Any]] = {}
    for raw in lifecycle_rows:
        row = _require_closed_fields(
            raw,
            _AUDIT_LIFECYCLE_FIELDS,
            label="semantic source audit claim lifecycle row",
        )
        claim_id = row.get("claim_id")
        claim = claims_by_id.get(claim_id) if isinstance(claim_id, str) else None
        if (
            claim is None
            or claim_id in lifecycle_by_id
            or row.get("claim_kind") != claim.get("claim_kind")
            or row.get("policy_lane") != claim.get("policy_lane")
            or not _string_sequence(row.get("emitted_files"))
            or not _string_in(
                row.get("builder_or_router_decision"),
                {"bot_delegated", "emitted", "not_seen_by_builder", "suppressed"},
            )
            or not _string_in(
                row.get("runtime_eligibility"), {"report_only", "runtime_candidate"}
            )
            or not _string_in(row.get("surface_gate_decision"), {"allowed", "rejected"})
            or row.get("quarantine_status") != "clear"
            or row.get("quarantine_reason") != ""
            or not (
                row.get("first_missing_link") is None
                or _string_in(
                    row.get("first_missing_link"),
                    {"builder_or_router", "runtime_surface", "source_eligibility"},
                )
            )
            or not _string_in(row.get("surface_gate_reason"), _SURFACE_GATE_REASONS)
            or not (
                row.get("suppressed_reason") is None
                or _string_in(
                    row.get("suppressed_reason"), _LIFECYCLE_SUPPRESSED_REASONS
                )
            )
            or row.get("operator_impact") != "diagnostic_only"
            or not _string_in(
                row.get("final_runtime_effect"),
                {
                "delegated_to_bot",
                "emitted_runtime_row",
                "not_emitted_by_builder_or_router",
                "suppressed_runtime_claim",
                },
            )
            or not (
                row.get("runtime_surface") is None
                or (
                    isinstance(row.get("runtime_surface"), str)
                    and re.fullmatch(r"[A-Za-z0-9_]+\.json", row["runtime_surface"])
                    is not None
                )
            )
        ):
            raise ReleaseGateError("semantic source audit claim lifecycle binding mismatch")
        lifecycle_by_id[claim_id] = row
    if set(lifecycle_by_id) != set(claims_by_id):
        raise ReleaseGateError("semantic source audit claim lifecycle binding mismatch")

    expected_summary = {
        "cards_total": len(card_rows),
        "cards_with_missing_links": sum(
            row["first_missing_link"] != "none" for row in card_rows.values()
        ),
        "cards_with_runtime_lowered_claims": sum(
            row["claim_lanes"].get("runtime_lowered", 0) > 0 for row in card_rows.values()
        ),
        "cards_with_suppressed_claims": sum(
            row["claim_lanes"].get("suppressed_with_reason", 0) > 0
            for row in card_rows.values()
        ),
        "claim_kind_policy_counts": dict(
            sorted(
                {
                    lane: sum(row["policy_lane"] == lane for row in claims_by_id.values())
                    for lane in {row["policy_lane"] for row in claims_by_id.values()}
                }.items()
            )
        ),
        "claim_lifecycle_decision_counts": dict(
            sorted(
                {
                    decision: sum(
                        row["builder_or_router_decision"] == decision
                        for row in lifecycle_by_id.values()
                    )
                    for decision in {
                        row["builder_or_router_decision"] for row in lifecycle_by_id.values()
                    }
                }.items()
            )
        ),
        "claims_total": len(claims_by_id),
        "report_only_claims": sum(row["lane"] == "report_only" for row in claims_by_id.values()),
        "runtime_evidence_required_claims": sum(
            row["policy_lane"] == "runtime_evidence_required" for row in claims_by_id.values()
        ),
        "runtime_lowered_claims": sum(
            row["lane"] == "runtime_lowered" for row in claims_by_id.values()
        ),
        "suppressed_claims": sum(
            row["lane"] == "suppressed_with_reason" for row in claims_by_id.values()
        ),
        "unsupported_or_unmapped_claims": sum(
            row["lane"] == "unsupported_or_unmapped" for row in claims_by_id.values()
        ),
    }
    if dict(summary) != expected_summary:
        raise ReleaseGateError("semantic source audit summary binding mismatch")
    return lifecycle_by_id


def _current_revision_path(outputs: Path, deck_name: str) -> Path:
    current = _load_json_file(outputs, PurePosixPath(deck_name, "current.json"))
    revision = current.get("revision")
    if not isinstance(revision, str):
        raise ReleaseGateError("current output revision is missing")
    pure = PurePosixPath(revision)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ReleaseGateError("current output revision is non-canonical")
    path = outputs / deck_name
    for part in pure.parts:
        path /= part
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ReleaseGateError("current output revision contains unsafe data")
    return path


def _claim_authority_lane(
    audit: Mapping[str, Any],
    disposition: str,
    *,
    deck_fingerprint: str,
    lifecycle: Mapping[str, Any],
) -> str:
    readiness = audit.get("claim_readiness")
    source_lane = audit.get("source_lane")
    policy_lane = audit.get("policy_lane")
    trust_ceiling = audit.get("trust_ceiling")
    source_type = audit.get("source_type")
    lane = audit.get("lane")
    authority = _validate_evidence_authority(audit, deck_fingerprint)
    if (
        policy_lane not in {"runtime_lowerable", "suppressed_or_conditional"}
        or lane
        not in {
            "runtime_lowered",
            "suppressed_with_reason",
            "unsupported_or_unmapped",
            "report_only",
        }
        or not isinstance(audit.get("strategic_receipt_verified"), bool)
    ):
        raise ReleaseGateError("semantic source authority combination mismatch")

    no_runtime_row = (
        not lifecycle.get("emitted_files")
        and lifecycle.get("runtime_surface") is None
        and lifecycle.get("builder_or_router_decision") != "emitted"
    )
    if disposition == "bot_delegated":
        if (
            readiness != "explicit_low_confidence"
            or authority is not None
            or trust_ceiling != "report_only"
            or source_lane
            not in {"", "archetype_matched_public_guide", "deck_matched_public_guide"}
            or source_type not in {"", "public_guide"}
            or policy_lane != "suppressed_or_conditional"
            or lane not in {"report_only", "suppressed_with_reason"}
            or audit.get("strategic_receipt_verified") is not False
            or lifecycle.get("builder_or_router_decision") != "bot_delegated"
            or lifecycle.get("final_runtime_effect") != "delegated_to_bot"
            or lifecycle.get("runtime_eligibility") != "report_only"
            or lifecycle.get("surface_gate_decision") != "rejected"
            or lifecycle.get("surface_gate_reason") != "bot_delegated"
            or lifecycle.get("suppressed_reason") != "bot_delegated"
            or not no_runtime_row
        ):
            raise ReleaseGateError(
                "semantic claim disposition is incompatible with authority lane"
            )
        return "E"

    if (
        readiness == "source_backed_static_semantics"
        and source_lane == ""
        and authority is None
        and trust_ceiling in {"static_semantics", "report_only"}
        and source_type in {"", "official_card_data"}
        and audit.get("strategic_receipt_verified") is False
    ):
        authority_lane = "A"
    elif (
        readiness == "guide_backed"
        and source_lane == "deck_matched_public_guide"
        and authority is not None
        and authority.get("lane") == "B"
        and trust_ceiling == "guide"
        and source_type in {"", "public_guide"}
        and audit.get("strategic_receipt_verified") is True
    ):
        authority_lane = "B"
    elif (
        readiness == "guide_backed"
        and source_lane
        in {"", "archetype_matched_public_guide", "deck_matched_public_guide"}
        and (authority is None or authority.get("lane") == "C")
        and trust_ceiling == "guide"
        and source_type in {"", "public_guide"}
        and audit.get("strategic_receipt_verified") is False
    ):
        authority_lane = "C"
    elif (
        readiness == "explicit_low_confidence"
        and source_lane in {"", "archetype_matched_public_guide"}
        and (authority is None or authority.get("lane") == "C")
        and trust_ceiling == "report_only"
        and source_type in {"", "public_guide"}
        and audit.get("strategic_receipt_verified") is False
    ):
        authority_lane = "C"
    else:
        raise ReleaseGateError("semantic source authority combination mismatch")

    return authority_lane


def _produce_semantic_rows(
    repository: Path, outputs: Path, receipt_relative: str
) -> dict[str, list[dict[str, Any]]]:
    inventory = _load_json_file(
        repository, PurePosixPath("tests/fixtures/near100/current_semantic_inventory.json")
    )
    catalog = _load_json_file(
        repository, PurePosixPath("docs/operator/audited-deck-catalog.json")
    )
    audited_decks = catalog.get("decks")
    if not isinstance(audited_decks, list):
        raise ReleaseGateError("canonical semantic inventory catalog is invalid")
    try:
        validate_semantic_inventory(inventory, audited_catalog=audited_decks)
    except ValueError as exc:
        raise ReleaseGateError("canonical semantic inventory is invalid") from exc
    decks = inventory.get("decks")
    if not isinstance(decks, list) or len(decks) != 12:
        raise ReleaseGateError("canonical semantic inventory deck count mismatch")
    card_rows: list[dict[str, Any]] = []
    semantic_claims = inventory.get("semantic_claims")
    if not isinstance(semantic_claims, list) or len(semantic_claims) != SEMANTIC_CLAIM_COUNT:
        raise ReleaseGateError("canonical semantic claim inventory count mismatch")
    expected_claim_ids: list[str] = []
    for raw in semantic_claims:
        try:
            canonical = canonical_semantic_claim(raw)
        except ValueError as exc:
            raise ReleaseGateError("canonical semantic claim inventory is invalid") from exc
        if not isinstance(raw, Mapping) or dict(raw) != canonical:
            raise ReleaseGateError("canonical semantic claim inventory is invalid")
        expected_claim_ids.append(canonical["claim_key"])
    if len(set(expected_claim_ids)) != SEMANTIC_CLAIM_COUNT:
        raise ReleaseGateError("canonical semantic claim inventory identities are invalid")
    claim_groups: dict[str, dict[str, Any]] = {}
    claim_occurrences = 0
    all_ids: set[str] = set()
    for deck in decks:
        if not isinstance(deck, Mapping) or not isinstance(deck.get("deck_name"), str):
            raise ReleaseGateError("canonical semantic inventory deck schema mismatch")
        deck_name = deck["deck_name"]
        revision = _current_revision_path(outputs, deck_name)
        reports = revision / "04_package" / "reports"
        ledger = _load_json_file(reports, PurePosixPath("disposition_ledger.json"))
        audit = _load_json_file(reports, PurePosixPath("source_contract_audit.json"))
        _require_closed_fields(ledger, _LEDGER_FIELDS, label="semantic disposition ledger")
        _require_closed_fields(audit, _AUDIT_FIELDS, label="semantic source audit")
        if ledger.get("deck_fingerprint") != deck.get("deck_fingerprint"):
            raise ReleaseGateError("semantic disposition ledger deck binding mismatch")
        if audit.get("deck_name") != deck_name:
            raise ReleaseGateError("semantic source audit deck binding mismatch")
        ledger_cards = ledger.get("cards")
        ledger_claims = ledger.get("claims")
        audit_claims = audit.get("claim_rows")
        if not isinstance(ledger_cards, list) or not isinstance(ledger_claims, list) or not isinstance(audit_claims, Mapping):
            raise ReleaseGateError("semantic report schema mismatch")
        lifecycle_by_id = _validate_source_audit(audit, ledger_cards, ledger_claims)
        expected_cards = [
            row["composite_card_key"]
            for row in (*deck.get("main_cards", ()), *deck.get("sideboard_modules", ()))
        ]
        expected_card_surfaces: dict[tuple[str, str], str] = {}
        for expected_row in deck.get("main_cards", ()):
            expected_card_surfaces[("main_deck", expected_row["card_id"])] = expected_row[
                "composite_card_key"
            ]
        for expected_row in deck.get("sideboard_modules", ()):
            expected_card_surfaces[
                ("sideboard_module", expected_row["card_id"])
            ] = expected_row["composite_card_key"]
        if len(ledger_cards) != len(expected_cards):
            raise ReleaseGateError("semantic report row count mismatch")
        cards_by_id: dict[str, Mapping[str, Any]] = {}
        for raw in ledger_cards:
            row = _require_closed_fields(
                raw, _LEDGER_CARD_FIELDS, label="semantic card disposition row"
            )
            official = row.get("official_semantics")
            card_id = official.get("GameCardId") if isinstance(official, Mapping) else None
            zone = row.get("zone")
            reported_identity = row.get("composite_card_key")
            if reported_identity in expected_cards:
                obligation_id = reported_identity
            else:
                obligation_id = (
                    expected_card_surfaces.get((zone, card_id))
                    if isinstance(zone, str) and isinstance(card_id, str)
                    else None
                )
            allowed_reported = {
                obligation_id,
                f"{deck['deck_fingerprint']}:{zone}:{card_id}",
            }
            if (
                not isinstance(obligation_id, str)
                or obligation_id in cards_by_id
                or row.get("deck_fingerprint") != deck.get("deck_fingerprint")
                or not isinstance(row.get("physical_owner"), str)
                or reported_identity not in allowed_reported
            ):
                raise ReleaseGateError("semantic card disposition identity mismatch")
            cards_by_id[obligation_id] = row
        claims_by_id: dict[str, Mapping[str, Any]] = {}
        for raw in ledger_claims:
            row = _require_closed_fields(
                raw, _LEDGER_CLAIM_FIELDS, label="semantic claim disposition row"
            )
            obligation_id = row.get("composite_claim_identity")
            claim_id = row.get("claim_id")
            if (
                not isinstance(obligation_id, str)
                or not isinstance(claim_id, str)
                or obligation_id in claims_by_id
                or row.get("deck_fingerprint") != deck.get("deck_fingerprint")
                or not isinstance(row.get("evidence_id"), str)
                or re.fullmatch(rf"(?:[A-E]:)?{re.escape(claim_id)}", row["evidence_id"])
                is None
            ):
                raise ReleaseGateError("semantic claim disposition identity mismatch")
            claims_by_id[obligation_id] = row
        if len(audit_claims) != len(ledger_claims):
            raise ReleaseGateError("semantic source audit row count mismatch")
        for claim_id, raw in audit_claims.items():
            row = _require_closed_audit_claim(raw)
            if not isinstance(claim_id, str) or row.get("claim_id") != claim_id:
                raise ReleaseGateError("semantic source audit claim identity mismatch")
        claim_ids = {row["claim_id"] for row in claims_by_id.values()}
        if set(audit_claims) != claim_ids:
            raise ReleaseGateError("semantic source audit identities do not match ledger")
        if set(cards_by_id) != set(expected_cards):
            raise ReleaseGateError("semantic report identities do not match canonical inventory")
        for obligation_id in expected_cards:
            row = cards_by_id[obligation_id]
            lane, disposition = row.get("authority_lane"), row.get("disposition")
            if lane not in {"A", "B", "C", "D", "E"} or disposition not in _FINAL_DISPOSITIONS:
                raise ReleaseGateError("card semantic disposition is invalid")
            if obligation_id in all_ids:
                raise ReleaseGateError("duplicate semantic obligation identity")
            all_ids.add(obligation_id)
            card_rows.append(
                {
                    "obligation_id": obligation_id,
                    "authority_lanes": [lane],
                    "final_disposition": True,
                    "evidence_paths": [receipt_relative],
                }
            )
        for row in claims_by_id.values():
            claim_id, disposition = row.get("claim_id"), row.get("disposition")
            audit_row = audit_claims.get(claim_id) if isinstance(claim_id, str) else None
            if disposition not in _FINAL_DISPOSITIONS or not isinstance(audit_row, Mapping):
                raise ReleaseGateError("claim semantic disposition is invalid")
            try:
                canonical = canonical_semantic_claim(audit_row)
            except ValueError as exc:
                raise ReleaseGateError("claim semantic source payload is invalid") from exc
            obligation_id = canonical["claim_key"]
            group = claim_groups.setdefault(
                obligation_id,
                {"authority_lanes": set(), "final_dispositions": []},
            )
            lifecycle = lifecycle_by_id.get(claim_id)
            if lifecycle is None:
                raise ReleaseGateError("semantic source audit claim lifecycle binding mismatch")
            authority_lane = _claim_authority_lane(
                audit_row,
                disposition,
                deck_fingerprint=deck["deck_fingerprint"],
                lifecycle=lifecycle,
            )
            if authority_lane == "E" and (
                lifecycle.get("emitted_files")
                or lifecycle.get("runtime_surface") is not None
                or lifecycle.get("builder_or_router_decision") == "emitted"
            ):
                raise ReleaseGateError(
                    "semantic claim disposition is incompatible with authority lane"
                )
            group["authority_lanes"].add(authority_lane)
            group["final_dispositions"].append(disposition in _FINAL_DISPOSITIONS)
            claim_occurrences += 1
    if claim_occurrences != _SEMANTIC_REPORT_CLAIM_OCCURRENCES:
        raise ReleaseGateError("semantic claim occurrence count mismatch")
    if set(claim_groups) != set(expected_claim_ids):
        raise ReleaseGateError("semantic report identities do not match canonical inventory")
    claim_rows: list[dict[str, Any]] = []
    for obligation_id in expected_claim_ids:
        group = claim_groups[obligation_id]
        lanes = sorted(group["authority_lanes"])
        final_dispositions = group["final_dispositions"]
        if len(lanes) != 1:
            raise ReleaseGateError("canonical semantic claim has ambiguous authority lanes")
        if not final_dispositions or not all(final_dispositions):
            raise ReleaseGateError("canonical semantic claim has a non-final occurrence")
        if obligation_id in all_ids:
            raise ReleaseGateError("duplicate semantic obligation identity")
        all_ids.add(obligation_id)
        claim_rows.append(
            {
                "obligation_id": obligation_id,
                "authority_lanes": lanes,
                "final_disposition": True,
                "evidence_paths": [receipt_relative],
            }
        )
    if len(card_rows) != SEMANTIC_CARD_MODULE_COUNT or len(claim_rows) != SEMANTIC_CLAIM_COUNT:
        raise ReleaseGateError("produced semantic closure count mismatch")
    return {"card_module_rows": card_rows, "claim_rows": claim_rows}


def _gh_json(repository: Path, *arguments: str) -> Any:
    completed = _execute_bounded(
        ("gh", *arguments),
        cwd=repository,
        env=_controlled_environment(repository),
        timeout=60,
    )
    if completed.returncode != 0:
        raise ReleaseGateError("live GitHub verification failed")
    return _load_json_bytes(completed.stdout.encode("utf-8"), source="live GitHub response")


_RULESET_SUMMARY_FIELDS = frozenset(
    {
        "id",
        "node_id",
        "name",
        "target",
        "source_type",
        "source",
        "enforcement",
        "created_at",
        "updated_at",
        "_links",
    }
)
_RULESET_DETAIL_FIELDS = _RULESET_SUMMARY_FIELDS | {
    "bypass_actors",
    "current_user_can_bypass",
    "conditions",
    "rules",
}


def _closed_github_mapping(
    value: Any,
    *,
    allowed: frozenset[str],
    required: frozenset[str],
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReleaseGateError(f"live GitHub {label} response schema mismatch")
    fields = set(value)
    if not required <= fields or not fields <= allowed:
        raise ReleaseGateError(f"live GitHub {label} response schema mismatch")
    return value


def _gh_paginated_rulesets(repository: Path, identity: str) -> tuple[Mapping[str, Any], ...]:
    pages = _gh_json(
        repository,
        "api",
        "--paginate",
        "--slurp",
        f"repos/{identity}/rulesets",
    )
    if not isinstance(pages, list) or any(not isinstance(page, list) for page in pages):
        raise ReleaseGateError("live GitHub ruleset pagination schema mismatch")
    rows: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    for page in pages:
        for raw in page:
            row = _closed_github_mapping(
                raw,
                allowed=_RULESET_SUMMARY_FIELDS,
                required=frozenset({"id", "name", "target", "enforcement"}),
                label="ruleset summary",
            )
            ruleset_id = row.get("id")
            if not isinstance(ruleset_id, int) or isinstance(ruleset_id, bool):
                raise ReleaseGateError("live GitHub branch ruleset identity is invalid")
            if ruleset_id in seen_ids:
                raise ReleaseGateError("live GitHub ruleset pagination contains duplicate identities")
            seen_ids.add(ruleset_id)
            rows.append(row)
    return tuple(sorted(rows, key=lambda row: (int(row["id"]), str(row["name"]))))


def _collect_live_github_state(repository: Path, snapshot: _GateSnapshot) -> dict[str, Any]:
    identity = snapshot.repository_identity
    settings = _gh_json(repository, "api", f"repos/{identity}")
    rulesets = _gh_paginated_rulesets(repository, identity)
    tag = _gh_json(repository, "api", f"repos/{identity}/git/ref/tags/v{__version__}")
    release = _gh_json(repository, "api", f"repos/{identity}/releases/tags/v{__version__}")
    if not isinstance(tag, Mapping) or not isinstance(tag.get("object"), Mapping):
        raise ReleaseGateError("live GitHub tag response schema mismatch")
    ref_object = tag["object"]
    peeled_oid = ref_object.get("sha")
    if ref_object.get("type") == "tag":
        annotated = _gh_json(repository, "api", f"repos/{identity}/git/tags/{peeled_oid}")
        if not isinstance(annotated, Mapping) or not isinstance(annotated.get("object"), Mapping):
            raise ReleaseGateError("live GitHub annotated tag response schema mismatch")
        peeled_oid = annotated["object"].get("sha")
    active_rulesets = [
        row
        for row in rulesets
        if row.get("enforcement") == "active" and row.get("target") == "branch"
    ]
    if len(active_rulesets) != 1:
        raise ReleaseGateError("live GitHub must expose exactly one active branch ruleset")
    ruleset_id = active_rulesets[0].get("id")
    if not isinstance(ruleset_id, int):
        raise ReleaseGateError("live GitHub branch ruleset identity is invalid")
    ruleset = _closed_github_mapping(
        _gh_json(repository, "api", f"repos/{identity}/rulesets/{ruleset_id}"),
        allowed=_RULESET_DETAIL_FIELDS,
        required=frozenset(
            {
                "id",
                "name",
                "target",
                "enforcement",
                "bypass_actors",
                "conditions",
                "rules",
            }
        ),
        label="ruleset detail",
    )
    if ruleset.get("id") != ruleset_id:
        raise ReleaseGateError("live GitHub ruleset detail identity mismatch")
    return {
        "schema_version": 1,
        "repository": identity,
        "commit_oid": snapshot.commit_oid,
        "tree_oid": snapshot.tree_oid,
        "release_tag": f"v{__version__}",
        "settings": settings,
        "ruleset": ruleset,
        "tag": {
            "ref_object_oid": ref_object.get("sha"),
            "object_type": ref_object.get("type"),
            "peeled_commit_oid": peeled_oid,
        },
        "release": release,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "transaction_id": uuid.uuid4().hex,
    }


def _validate_live_github_state(state: Mapping[str, Any], snapshot: _GateSnapshot) -> None:
    expected_fields = {
        "schema_version", "repository", "commit_oid", "tree_oid", "release_tag",
        "settings", "ruleset", "tag", "release", "observed_at", "transaction_id",
    }
    schema_version = state.get("schema_version")
    if (
        set(state) != expected_fields
        or type(schema_version) is not int
        or schema_version != 1
    ):
        raise ReleaseGateError("live GitHub transaction schema mismatch")
    if (
        state.get("repository") != snapshot.repository_identity
        or state.get("commit_oid") != snapshot.commit_oid
        or state.get("tree_oid") != snapshot.tree_oid
        or state.get("release_tag") != f"v{__version__}"
    ):
        raise ReleaseGateError("live GitHub transaction repository/release binding mismatch")
    transaction_id = state.get("transaction_id")
    if not isinstance(transaction_id, str) or re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None:
        raise ReleaseGateError("live GitHub transaction identity mismatch")
    try:
        observed = datetime.fromisoformat(str(state.get("observed_at")).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReleaseGateError("live GitHub observation time invalid") from exc
    if observed.tzinfo is None:
        raise ReleaseGateError("live GitHub observation time invalid")
    age = abs((datetime.now(timezone.utc) - observed).total_seconds())
    if age > _FINAL_EVIDENCE_MAX_AGE_SECONDS:
        raise ReleaseGateError("live GitHub observation is stale")
    settings, ruleset, tag, release = (
        state.get("settings"), state.get("ruleset"), state.get("tag"), state.get("release")
    )
    if not all(isinstance(value, Mapping) for value in (settings, ruleset, tag, release)):
        raise ReleaseGateError("live GitHub transaction payload schema mismatch")
    if (
        settings.get("full_name") != snapshot.repository_identity
        or settings.get("default_branch") != "main"
        or settings.get("archived") is not False
        or settings.get("disabled") is not False
        or settings.get("visibility") != "public"
        or settings.get("has_issues") is not True
        or settings.get("has_projects") is not False
        or settings.get("has_wiki") is not False
        or settings.get("has_discussions") is not False
        or settings.get("allow_squash_merge") is not True
        or settings.get("allow_merge_commit") is not False
        or settings.get("allow_rebase_merge") is not False
        or settings.get("allow_auto_merge") is not False
        or settings.get("delete_branch_on_merge") is not True
    ):
        raise ReleaseGateError("live GitHub repository settings do not satisfy release policy")
    ruleset_conditions = ruleset.get("conditions")
    ruleset_ref_name = (
        ruleset_conditions.get("ref_name")
        if isinstance(ruleset_conditions, Mapping)
        else None
    )
    rules = ruleset.get("rules")
    rules_are_closed = isinstance(rules, list) and all(
        isinstance(row, Mapping)
        and set(row) == {"type"}
        and isinstance(row.get("type"), str)
        for row in rules
    )
    rule_types = {row["type"] for row in rules} if rules_are_closed else set()
    if (
        not set(ruleset) <= _RULESET_DETAIL_FIELDS
        or
        not isinstance(ruleset.get("id"), int)
        or isinstance(ruleset.get("id"), bool)
        or ruleset.get("name") != "main-linear-signed"
        or ruleset.get("target") != "branch"
        or ruleset.get("enforcement") != "active"
        or ruleset.get("bypass_actors") != []
        or not isinstance(ruleset_conditions, Mapping)
        or set(ruleset_conditions) != {"ref_name"}
        or not isinstance(ruleset_ref_name, Mapping)
        or set(ruleset_ref_name) != {"include", "exclude"}
        or ruleset_ref_name.get("include") != ["refs/heads/main"]
        or ruleset_ref_name.get("exclude") != []
        or not rules_are_closed
        or rule_types
        != {"deletion", "non_fast_forward", "required_linear_history", "required_signatures"}
    ):
        raise ReleaseGateError("live GitHub branch ruleset does not satisfy release policy")
    if tag.get("peeled_commit_oid") != snapshot.commit_oid:
        raise ReleaseGateError("live GitHub tag does not resolve to release commit")
    if (
        not isinstance(release.get("id"), int)
        or isinstance(release.get("id"), bool)
        or release.get("tag_name") != f"v{__version__}"
        or release.get("draft") is not False
        or release.get("prerelease") is not False
        or not isinstance(release.get("html_url"), str)
        or not isinstance(release.get("assets"), list)
        or release.get("assets") != []
    ):
        raise ReleaseGateError("live GitHub release payload does not satisfy release policy")


_RECEIPT_BINDING_FIELDS = (
    "repository_identity",
    "commit_oid",
    "tree_oid",
    "tree_state",
    "dirty_tree_fingerprint",
    "generation_mode",
)


def _receipt_binding(
    meta: Mapping[str, Any], *, github_state: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    binding = {field: meta[field] for field in _RECEIPT_BINDING_FIELDS}
    if github_state is not None:
        binding.update(
            {
                "transaction_id": github_state["transaction_id"],
                "observed_at": github_state["observed_at"],
            }
        )
    return binding


def _release_check_receipt(
    *, check_id: str, source: ReleaseCheck, binding: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "producer": "hsconfig.release_gate.base_check",
        "check_id": check_id,
        "binding": dict(binding),
        "result": {"passed": source.passed},
    }


def _validated_success_receipt(
    *, producer: str, check_id: str, binding: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "producer": producer,
        "check_id": check_id,
        "binding": dict(binding),
        "result": {"passed": True},
    }


def _build_base_evidence(
    *, repository: Path, outputs_root: Path, checks: Sequence[ReleaseCheck],
    tree_mode: TreeMode, snapshot: _GateSnapshot,
) -> dict[str, Any]:
    by_name = {check.name: check for check in checks}
    failed_checks = sorted(check.name for check in checks if not check.passed)
    if failed_checks:
        raise ReleaseGateError("base evidence cannot be produced from failed checks")
    score_mode = "final" if tree_mode == "final" else "pre_cutover"
    github_state: Mapping[str, Any] | None = None
    if score_mode == "final":
        collected = _collect_live_github_state(repository, snapshot)
        _validate_live_github_state(collected, snapshot)
        github_state = collected
    state, fingerprint = _dirty_tree_fingerprint(repository)
    evidence_meta: dict[str, Any] = {
        "producer": "hsconfig.release_gate.base_evidence",
        "repository_root": str(repository),
        "repository_identity": snapshot.repository_identity,
        "version": __version__,
        "commit_oid": snapshot.commit_oid,
        "tree_oid": snapshot.tree_oid,
        "tree_state": state,
        "dirty_tree_fingerprint": fingerprint,
        "generation_mode": score_mode,
    }
    if github_state is not None:
        evidence_meta.update(
            {
                "transaction_id": github_state["transaction_id"],
                "observed_at": github_state["observed_at"],
            }
        )
    base_binding = _receipt_binding(evidence_meta)
    check_ids = set(ATOMIC_CHECK_OWNERS)
    if score_mode == "pre_cutover":
        check_ids -= _GITHUB_CHECK_IDS
    atomic: dict[str, Any] = {}
    receipts: dict[str, Any] = {}
    for check_id in sorted(check_ids):
        receipt_id = f"receipts/{check_id}.json"
        if check_id in _GITHUB_CHECK_IDS:
            if github_state is None:
                raise ReleaseGateError("final GitHub transaction evidence is missing")
            passed = True
            receipts[receipt_id] = _validated_success_receipt(
                producer="hsconfig.release_gate.base_check",
                check_id=check_id,
                binding=_receipt_binding(
                    evidence_meta,
                    github_state=github_state,
                ),
            )
        else:
            source = by_name[_atomic_release_check(check_id)]
            passed = source.passed
            receipts[receipt_id] = _release_check_receipt(
                check_id=check_id,
                source=source,
                binding=base_binding,
            )
        atomic[check_id] = {
            "passed": passed,
            "kind": (
                "coverage_json"
                if check_id in {"branch_coverage", "critical_coverage"}
                else "completed_base_check"
            ),
            "evidence_paths": [receipt_id],
            "blocking_reasons": [] if passed else ["release check failed"],
            "non_blocking_reasons": [],
            "scope": "PRE_RUN_CONTRACT",
            "owner": ATOMIC_CHECK_OWNERS[check_id],
        }
    semantic_receipt = "receipts/semantic_obligations.json"
    rows = _produce_semantic_rows(repository, outputs_root, semantic_receipt)
    receipts[semantic_receipt] = _validated_success_receipt(
        producer="hsconfig.semantic_inventory",
        check_id="semantic_obligations",
        binding=base_binding,
    )
    evidence = {
        "_meta": evidence_meta,
        "checks": atomic,
        "semantic_obligations": rows,
        "findings": {"open_p0": 0, "open_p1": 0},
    }
    return {"schema_version": 1, "evidence": evidence, "receipts": receipts}


def run_release_gate(
    *,
    repository: Path,
    outputs_root: Path,
    tree_mode: TreeMode = "final",
    owner_repository: Path | None = None,
) -> ReleaseGateResult:
    """Run every local release check in canonical order and fail closed."""
    root, outputs, commit_oid = _validate_repository(
        repository,
        outputs_root,
        tree_mode,
        owner_repository=owner_repository,
    )
    owner = (
        Path(owner_repository).resolve(strict=True)
        if owner_repository is not None
        else None
    )
    _verify_module_binding(root)
    snapshot = _capture_snapshot(
        root,
        outputs,
        owner_repository=owner,
    )
    if snapshot.commit_oid != commit_oid:
        raise ReleaseGateError("repository changed during release gate startup")
    specs = _command_specs(
        root,
        outputs,
        tree_mode,
        owner_repository=owner,
    )
    checks: list[ReleaseCheck] = []
    for spec in specs[:-1]:
        checks.append(_run_one(spec, repository=root))
    _assert_snapshot_unchanged(
        root,
        outputs,
        snapshot,
        owner_repository=owner,
    )
    if all(check.passed for check in checks):
        try:
            bundle = _build_base_evidence(
                repository=root,
                outputs_root=outputs,
                checks=checks,
                tree_mode=tree_mode,
                snapshot=snapshot,
            )
            near100 = specs[-1]
            stdin_data = json.dumps(
                bundle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            checks.append(
                _run_one(
                    near100,
                    repository=root,
                    stdin_data=stdin_data,
                )
            )
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            near100 = specs[-1]
            checks.append(
                ReleaseCheck(
                    name=near100.name,
                    passed=False,
                    command=near100.command,
                    details={
                        "returncode": None,
                        "error": _redact_text(f"base_evidence_failed:{exc}"),
                    },
                )
            )
    else:
        near100 = specs[-1]
        checks.append(
            ReleaseCheck(
                name=near100.name,
                passed=False,
                command=near100.command,
                details={"returncode": None, "error": "blocked_by_failed_prerequisite"},
            )
        )
    _assert_snapshot_unchanged(
        root,
        outputs,
        snapshot,
        owner_repository=owner,
    )
    if tuple(check.name for check in checks) != CHECK_NAMES:
        raise ReleaseGateError("release check composition drifted")
    passed = all(check.passed for check in checks)
    return ReleaseGateResult(
        passed=passed,
        final_release_ready=passed and tree_mode == "final",
        version=__version__,
        commit_oid=commit_oid,
        checks=tuple(checks),
    )


def _tracked_paths(repository: Path) -> tuple[str, ...]:
    raw = _git(repository, "ls-files", "-z", text=False)
    if not isinstance(raw, bytes):
        raise ReleaseGateError("tracked file inspection returned text")
    return tuple(sorted(value.decode("utf-8") for value in raw.split(b"\0") if value))


def _prospective_paths(repository: Path) -> tuple[str, ...]:
    raw = _git(
        repository,
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
        text=False,
    )
    if not isinstance(raw, bytes):
        raise ReleaseGateError("prospective file inspection returned text")
    return tuple(sorted(value.decode("utf-8") for value in raw.split(b"\0") if value))


def _text_violations(relative: str, data: bytes, *, public_doc: bool) -> list[str]:
    return publishable_text_violations(
        relative,
        data,
        public_doc=public_doc,
        contains_secret_fn=_contains_secret,
        source_todo_allowlist=SOURCE_TODO_ALLOWLIST,
        placeholder_reference_sha256=_EXACT_PLACEHOLDER_REFERENCE_SHA256,
        version=__version__,
    )


def _path_violations(relative: str) -> list[str]:
    return publishable_path_violations(relative)


def _archive_rows(path: Path) -> tuple[tuple[str, bytes], ...]:
    rows: list[tuple[str, bytes]] = []
    canonical: set[str] = set()
    windows_keys: dict[str, str] = {}

    def record(name: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in name):
            raise ReleaseGateError(f"archive member path contains ASCII control character: {name!r}")
        if not name or "\\" in name or name.startswith(("/", "//")) or re.match(r"^[A-Za-z]:", name):
            raise ReleaseGateError(f"archive member has non-canonical absolute path: {name}")
        candidate = name[:-1] if name.endswith("/") else name
        parts = candidate.split("/")
        if not candidate or any(part in {"", ".", ".."} for part in parts):
            raise ReleaseGateError(f"archive member has traversal/non-canonical path: {name}")
        if any(part.rstrip(" .") != part or ":" in part for part in parts):
            raise ReleaseGateError(f"archive member has unsafe path: {name}")
        normalized = "/".join(parts)
        folded = "/".join(part.casefold() for part in parts)
        if normalized in canonical:
            raise ReleaseGateError(f"archive duplicate member: {name}")
        previous = windows_keys.get(folded)
        if previous is not None and previous != normalized:
            raise ReleaseGateError(f"archive casefold collision: {previous}:{normalized}")
        canonical.add(normalized)
        windows_keys[folded] = normalized
        return normalized

    def read_bounded(stream: Any, *, expected: int, member_name: str) -> bytes:
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = stream.read(min(1024 * 1024, expected - size + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > expected or size > _MAX_ARCHIVE_MEMBER_BYTES:
                raise ReleaseGateError(f"archive member exceeds declared/size limit: {member_name}")
            chunks.append(chunk)
        if size != expected:
            raise ReleaseGateError(f"archive member size does not match header: {member_name}")
        return b"".join(chunks)

    archive_data = _secure_read_bytes(
        path.parent,
        PurePosixPath(path.name),
        context="distribution archive",
        max_bytes=_MAX_ARCHIVE_TOTAL_BYTES,
    )
    total_declared = 0
    if path.suffix == ".whl":
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            members = archive.infolist()
            if len(members) > _MAX_ARCHIVE_MEMBERS:
                raise ReleaseGateError("archive member count exceeds limit")
            for member in members:
                raw_name = member.orig_filename
                normalized = record(raw_name)
                mode = member.external_attr >> 16
                member_type = stat.S_IFMT(mode)
                if stat.S_ISLNK(mode) or member_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise ReleaseGateError(f"archive non-regular zip member: {member.filename}")
                directory = raw_name.endswith("/")
                if (directory and member_type not in {0, stat.S_IFDIR}) or (
                    not directory and member_type == stat.S_IFDIR
                ):
                    raise ReleaseGateError(f"archive zip member type/name mismatch: {member.filename}")
                if directory:
                    continue
                if member.file_size > _MAX_ARCHIVE_MEMBER_BYTES:
                    raise ReleaseGateError(f"archive member exceeds size limit: {member.filename}")
                total_declared += member.file_size
                if total_declared > _MAX_ARCHIVE_TOTAL_BYTES:
                    raise ReleaseGateError("archive uncompressed content exceeds size limit")
                if member.file_size and member.compress_size == 0:
                    raise ReleaseGateError(f"archive member has invalid compressed size: {member.filename}")
                if member.compress_size and member.file_size / member.compress_size > _MAX_ARCHIVE_COMPRESSION_RATIO:
                    raise ReleaseGateError(f"archive member compression ratio exceeds limit: {member.filename}")
                with archive.open(member, "r") as stream:
                    rows.append(
                        (normalized, read_bounded(stream, expected=member.file_size, member_name=member.filename))
                    )
    else:
        tar_index: list[tuple[str, str, int, bool]] = []
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as archive:
            for member_number, member in enumerate(archive, start=1):
                if member_number > _MAX_ARCHIVE_MEMBERS:
                    raise ReleaseGateError("archive member count exceeds limit")
                normalized = record(member.name)
                if member.issym() or member.islnk():
                    raise ReleaseGateError(f"archive link member is forbidden: {member.name}")
                if member.isdir():
                    tar_index.append((member.name, normalized, 0, True))
                    continue
                if not member.isfile():
                    raise ReleaseGateError(f"archive non-regular tar member: {member.name}")
                if member.size > _MAX_ARCHIVE_MEMBER_BYTES:
                    raise ReleaseGateError(f"archive member exceeds size limit: {member.name}")
                total_declared += member.size
                if total_declared > _MAX_ARCHIVE_TOTAL_BYTES:
                    raise ReleaseGateError("archive uncompressed content exceeds size limit")
                tar_index.append((member.name, normalized, member.size, False))
        compressed_bytes = len(archive_data)
        if total_declared and (
            compressed_bytes <= 0
            or total_declared / compressed_bytes > _MAX_ARCHIVE_COMPRESSION_RATIO
        ):
            raise ReleaseGateError("archive compression ratio exceeds limit")
        # Reopen only after the complete bounded header pass has proved the
        # member count, declared sizes, types, paths and aggregate ratio. This
        # avoids getmembers() materialization and reads no member payload before
        # the resource limits have passed.
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as archive:
            observed = 0
            for member in archive:
                if observed >= len(tar_index):
                    raise ReleaseGateError("archive changed between validation and read")
                expected_name, normalized, expected_size, directory = tar_index[observed]
                observed += 1
                if (
                    member.name != expected_name
                    or member.size != expected_size
                    or member.isdir() is not directory
                    or (not directory and not member.isfile())
                ):
                    raise ReleaseGateError("archive changed between validation and read")
                if directory:
                    continue
                stream = archive.extractfile(member)
                if stream is None:
                    raise ReleaseGateError(f"archive member cannot be read: {member.name}")
                with stream:
                    rows.append(
                        (
                            normalized,
                            read_bounded(
                                stream,
                                expected=member.size,
                                member_name=member.name,
                            ),
                        )
                    )
            if observed != len(tar_index):
                raise ReleaseGateError("archive changed between validation and read")
    if sum(len(data) for _, data in rows) > _MAX_ARCHIVE_TOTAL_BYTES:
        raise ReleaseGateError("archive uncompressed content exceeds size limit")
    return tuple(rows)


def _secure_tracked_path(repository: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ReleaseGateError(f"non-canonical tracked path: {relative}")
    source = repository
    for index, part in enumerate(pure.parts):
        source = source / part
        try:
            metadata = source.lstat()
        except OSError as exc:
            raise ReleaseGateError(f"tracked source cannot be inspected: {relative}") from exc
        final = index == len(pure.parts) - 1
        expected = stat.S_ISREG(metadata.st_mode) if final else stat.S_ISDIR(metadata.st_mode)
        if not expected or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise ReleaseGateError(f"tracked source contains link/reparse/non-regular data: {relative}")
        if final and getattr(metadata, "st_nlink", 1) not in {0, 1}:
            raise ReleaseGateError(f"tracked source must not be a hardlink: {relative}")
    return source


def _stage_tracked_source(repository: Path, target: Path) -> None:
    """Copy only regular tracked files into an isolated build source tree."""
    for relative in _tracked_paths(repository):
        pure = PurePosixPath(relative)
        destination = target.joinpath(*pure.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            _secure_read_bytes(
                repository,
                pure,
                context="tracked distribution source",
            )
        )


def _scan_distributions(repository: Path) -> tuple[list[str], int]:
    violations: list[str] = []
    count = 0
    build_environment = _distribution_build_environment(repository)
    with TemporaryDirectory(prefix="hsconfig-release-distribution-") as temporary:
        target = Path(temporary)
        source = target / "source"
        artifacts_root = target / "artifacts"
        try:
            _stage_tracked_source(repository, source)
        except (OSError, ReleaseGateError) as exc:
            return ([f"distribution_source_staging_failed:{exc}"], 0)
        completed = _execute_bounded(
            (
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(artifacts_root),
                str(source),
            ),
            cwd=source,
            env=build_environment,
            timeout=1_200,
        )
        if completed.returncode != 0:
            return ([f"distribution_build_failed:returncode={completed.returncode}"], 0)
        artifacts = sorted((*artifacts_root.glob("*.whl"), *artifacts_root.glob("*.tar.gz")))
        if len(artifacts) != 2:
            return ([f"distribution_artifact_count:{len(artifacts)}"], 0)
        for artifact in artifacts:
            count += 1
            for member, data in _archive_rows(artifact):
                relative = f"{artifact.name}!{member}"
                violations.extend(_path_violations(relative))
                violations.extend(_text_violations(relative, data, public_doc=False))
    return violations, count


def _catalog_deck_names(repository: Path) -> tuple[str, ...]:
    catalog_document = _load_json_bytes(
        _secure_read_bytes(
            repository,
            PurePosixPath("docs", "operator", "audited-deck-catalog.json"),
            context="current package catalog",
        ),
        source="docs/operator/audited-deck-catalog.json",
    )
    if not isinstance(catalog_document, Mapping):
        raise ReleaseGateError("current package catalog schema mismatch")
    try:
        deck_names = tuple(row["deck_name"] for row in catalog_document["decks"])
    except (KeyError, TypeError) as exc:
        raise ReleaseGateError("current package catalog schema mismatch") from exc
    if len(deck_names) != 12 or len(set(deck_names)) != 12:
        raise ReleaseGateError("current package catalog count mismatch")
    if any(
        not isinstance(name, str)
        or name in {"", ".", ".."}
        or any(character in name for character in "/\\:")
        for name in deck_names
    ):
        raise ReleaseGateError("current package catalog deck name mismatch")
    return deck_names


def _current_package_files(
    repository: Path, outputs_root: Path
) -> tuple[list[tuple[str, bytes]], list[str], int]:
    violations: list[str] = []
    rows: list[tuple[str, bytes]] = []
    try:
        deck_names = _catalog_deck_names(repository)
    except ReleaseGateError as exc:
        return rows, [str(exc)], 0
    try:
        actual_root_entries = {entry.name for entry in os.scandir(outputs_root)}
    except OSError as exc:
        return rows, [f"outputs_root_unreadable:{exc}"], 0
    unexpected = sorted(actual_root_entries - set(deck_names))
    missing = sorted(set(deck_names) - actual_root_entries)
    violations.extend(f"unexpected outputs root entry:{name}" for name in unexpected)
    violations.extend(f"missing outputs deck root:{name}" for name in missing)
    scanned = 0
    for deck_name in deck_names:
        deck_root = outputs_root / deck_name
        try:
            relative_current = PurePosixPath(deck_name, "current.json")
            current_data = _secure_read_bytes(
                outputs_root,
                relative_current,
                context="current package pointer",
            )
            current = _load_json_bytes(current_data, source=relative_current.as_posix())
            required_current = {
                "schema_version", "deck_name", "deck_fingerprint", "content_root_sha256", "revision"
            }
            if not isinstance(current, Mapping) or set(current) != required_current:
                raise ValueError("current pointer schema mismatch")
            if current.get("schema_version") != 1 or current.get("deck_name") != deck_name:
                raise ValueError("current pointer identity mismatch")
            for digest_field in ("deck_fingerprint", "content_root_sha256"):
                if not isinstance(current.get(digest_field), str) or re.fullmatch(r"[0-9a-f]{64}", current[digest_field]) is None:
                    raise ValueError(f"current pointer {digest_field} mismatch")
            revision = current["revision"]
            if not isinstance(revision, str):
                raise ValueError("revision must be a string")
            pure = PurePosixPath(revision)
            if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
                raise ValueError("non-canonical revision")
            if pure.name != f"sha256-{current['content_root_sha256']}":
                raise ValueError("current pointer content root binding mismatch")
            package = deck_root
            for part in pure.parts:
                package = package / part
                metadata = package.lstat()
                if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                    raise ValueError("revision contains link/reparse/non-directory")
            rows.append((relative_current.as_posix(), current_data))
        except (OSError, UnicodeError, KeyError, TypeError, ValueError, ReleaseGateError) as exc:
            violations.append(f"current_package_invalid:{deck_name}:{exc}")
            continue
        try:
            package_rows = _walk_regular_tree(
                package, context=f"current package {deck_name}"
            )
        except (OSError, ReleaseGateError) as exc:
            violations.append(f"current_package_non_regular_or_link:{deck_name}:{exc}")
            continue
        scanned += 1
        for package_relative, path, metadata in package_rows:
            relative = path.relative_to(outputs_root).as_posix()
            try:
                data = _secure_read_bytes(
                    package,
                    PurePosixPath(package_relative),
                    context=f"current package {deck_name}",
                    expected_identity=_stat_identity(metadata),
                )
            except ReleaseGateError as exc:
                violations.append(f"current_package_changed:{deck_name}:{exc}")
                scanned -= 1
                break
            rows.append((relative, data))
    try:
        output_rows = _walk_regular_tree(outputs_root, context="outputs tree")
    except (OSError, ReleaseGateError) as exc:
        violations.append(f"outputs_tree_non_regular_or_link:{exc}")
    else:
        for relative, _path, _metadata in output_rows:
            violations.extend(_path_violations(relative))
    return rows, violations, scanned


def _scan_current_packages(repository: Path, outputs_root: Path) -> tuple[list[str], int]:
    rows, violations, scanned = _current_package_files(repository, outputs_root)
    for relative, data in rows:
        violations.extend(_path_violations(relative))
        violations.extend(_text_violations(relative, data, public_doc=False))
    return violations, scanned


def _outputs_inventory_sha256(repository: Path, outputs_root: Path) -> str:
    rows, violations, count = _current_package_files(repository, outputs_root)
    if violations or count != 12:
        raise ReleaseGateError("outputs inventory cannot be bound safely: " + ";".join(violations[:5]))
    expected = set(_catalog_deck_names(repository))
    inventory: list[tuple[str, str, int, str]] = []

    def hash_file(relative: PurePosixPath, metadata: os.stat_result) -> tuple[int, str]:
        data = _secure_read_bytes(
            outputs_root,
            relative,
            context="outputs inventory file",
            expected_identity=_stat_identity(metadata),
        )
        if len(data) != metadata.st_size:
            raise ReleaseGateError("outputs file changed while inventory was captured")
        return len(data), hashlib.sha256(data).hexdigest()

    def visit(directory: Path, prefix: PurePosixPath) -> tuple[int, str]:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name.casefold())
        except OSError as exc:
            raise ReleaseGateError("outputs directory cannot be inspected") from exc
        seen: set[str] = set()
        child_rows: list[tuple[str, str, int, str]] = []
        total_size = 0
        for entry in entries:
            folded = entry.name.casefold()
            if folded in seen:
                raise ReleaseGateError("outputs tree contains a casefold collision")
            seen.add(folded)
            path = Path(entry.path)
            metadata = path.lstat()
            relative = prefix / entry.name
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise ReleaseGateError("outputs tree contains link/reparse data")
            if stat.S_ISDIR(metadata.st_mode):
                size, content_digest = visit(path, relative)
                row = (relative.as_posix(), "directory", size, content_digest)
            elif stat.S_ISREG(metadata.st_mode) and getattr(metadata, "st_nlink", 1) in {0, 1}:
                size, content_digest = hash_file(relative, metadata)
                row = (relative.as_posix(), "file", size, content_digest)
            else:
                raise ReleaseGateError("outputs tree contains hardlink/non-regular data")
            total_size += row[2]
            child_rows.append(row)
            inventory.append(row)
        digest = hashlib.sha256()
        for row in child_rows:
            digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
        return total_size, digest.hexdigest()

    root_metadata = outputs_root.lstat()
    if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(root_metadata.st_mode) or _is_reparse(root_metadata):
        raise ReleaseGateError("outputs root is not a regular directory")
    root_names = {entry.name for entry in os.scandir(outputs_root)}
    unexpected = sorted(root_names - expected)
    missing = sorted(expected - root_names)
    if unexpected:
        raise ReleaseGateError(f"unexpected outputs root entry: {unexpected[0]}")
    if missing:
        raise ReleaseGateError(f"missing outputs deck root: {missing[0]}")
    _size, root_digest = visit(outputs_root, PurePosixPath())
    digest = hashlib.sha256()
    digest.update(root_digest.encode("ascii") + b"\0")
    for row in sorted(inventory):
        digest.update(json.dumps(row, separators=(",", ":")).encode("utf-8") + b"\n")
    return digest.hexdigest()


def scan_publishable_content(
    *,
    repository: Path,
    outputs_root: Path,
    tree_mode: TreeMode,
    build_distributions: bool = True,
) -> dict[str, Any]:
    """Scan tracked sources, release archives, and the twelve current packages."""
    root = Path(repository).resolve()
    outputs = Path(outputs_root).resolve()
    violations: list[str] = []
    tracked_count = 0
    read_violations: list[str] = []

    def bound_read(relative: str) -> bytes:
        try:
            return _secure_read_bytes(
                root,
                PurePosixPath(relative),
                context="publishable tracked source",
            )
        except ReleaseGateError as exc:
            read_violations.append(f"tracked_non_regular:{relative}:{exc}")
            return b""

    try:
        tree_document = evaluate_repository_tree(
            root,
            mode=tree_mode,
            read_bytes=bound_read,
        )
    except (OSError, RuntimeError, TypeError, ValueError, PublishableTreeError) as exc:
        tree_document = {
            "passed": False,
            "violations": [f"publishable_tree_invalid:{exc}"],
            "files_scanned": 0,
        }
    tracked_count = int(tree_document["files_scanned"])
    violations.extend(str(row) for row in tree_document["violations"])
    violations.extend(read_violations)
    package_violations, package_count = _scan_current_packages(root, outputs)
    violations.extend(package_violations)
    artifact_count = 0
    if build_distributions:
        artifact_violations, artifact_count = _scan_distributions(root)
        violations.extend(artifact_violations)
    unique = tuple(sorted(set(violations)))
    return {
        "passed": not unique,
        "violations": list(unique),
        "tracked_files_scanned": tracked_count,
        "current_packages_scanned": package_count,
        "distribution_artifacts_scanned": artifact_count,
    }


def check_repository_hygiene(repository: Path, outputs_root: Path) -> dict[str, Any]:
    root = Path(repository).resolve()
    status = str(_git(root, "status", "--porcelain=v1", "--untracked-files=all"))
    violations = [f"dirty:{line}" for line in status.splitlines() if line]
    tracked = _tracked_paths(root)
    violations.extend(
        f"tracked_residue:{path}"
        for path in tracked
        if f"residue:{path}" in publishable_path_violations(path)
    )
    def inspect_workspace(directory: Path, prefix: PurePosixPath) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError:
            violations.append(f"workspace_unreadable:{prefix.as_posix() or '.'}")
            return
        seen: set[str] = set()
        for entry in entries:
            if not prefix.parts and entry.name == ".git":
                continue
            relative = prefix / entry.name
            key = entry.name.casefold()
            if key in seen:
                violations.append(f"workspace_collision:{relative.as_posix()}")
                continue
            seen.add(key)
            path = Path(entry.path)
            try:
                metadata = path.lstat()
            except OSError:
                violations.append(f"workspace_unreadable:{relative.as_posix()}")
                continue
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                violations.append(f"workspace_unsafe:{relative.as_posix()}")
                continue
            if stat.S_ISDIR(metadata.st_mode):
                if _LIVE_RESIDUE_DIRECTORY.fullmatch(entry.name):
                    violations.append(f"workspace_residue:{relative.as_posix()}")
                inspect_workspace(path, relative)
            elif stat.S_ISREG(metadata.st_mode):
                if getattr(metadata, "st_nlink", 1) not in {0, 1}:
                    violations.append(f"workspace_unsafe:{relative.as_posix()}")
                if _LIVE_RESIDUE_FILE.fullmatch(entry.name):
                    violations.append(f"workspace_residue:{relative.as_posix()}")
            else:
                violations.append(f"workspace_unsafe:{relative.as_posix()}")

    inspect_workspace(root, PurePosixPath())
    output_violations, package_count = _scan_current_packages(root, outputs_root)
    violations.extend(row for row in output_violations if row.startswith("residue:"))
    unique = tuple(sorted(set(violations)))
    return {
        "passed": not unique,
        "violations": list(unique),
        "current_packages": package_count,
    }


__all__ = [
    "CHECK_NAMES",
    "ReleaseCheck",
    "ReleaseGateError",
    "ReleaseGateResult",
    "check_repository_hygiene",
    "run_release_gate",
    "scan_publishable_content",
]
