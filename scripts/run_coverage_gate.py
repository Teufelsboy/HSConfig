from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import ast
import csv
import base64
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from importlib import abc as importlib_abc
from importlib import metadata as importlib_metadata
from importlib.machinery import ModuleSpec, SourceFileLoader
from importlib.resources.abc import Traversable, TraversableResources
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import tomllib
from typing import Any
from types import ModuleType
import zipfile

from _pytest.config import hookimpl
from _pytest.stash import StashKey


ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / f"pylock.{sys.version_info.major}.{sys.version_info.minor}.toml"
CHECKER_TIMEOUT_SECONDS = 120
BOUND_SCAN_TIMEOUT_SECONDS = 120
PYTEST_TIMEOUT_SECONDS = 14_400
WINDOWS_DELETE_SETTLE_TIMEOUT_SECONDS = 5.0
WINDOWS_DELETE_SETTLE_POLL_SECONDS = 0.01
WINDOWS_QUARANTINE_RENAME_TIMEOUT_SECONDS = 1.0
WINDOWS_QUARANTINE_RENAME_POLL_SECONDS = 0.01
CAPTURE_LIMIT = 64 * 1024
MAX_BOUND_SCAN_REQUEST_BYTES = 32 * 1024
MAX_BOUND_SCAN_RESPONSE_BYTES = CAPTURE_LIMIT
MAX_COVERAGE_JSON_BYTES = 256 * 1024 * 1024
MAX_LOCK_BYTES = 4 * 1024 * 1024
MAX_RUNTIME_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_RUNTIME_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_PYTEST_FAILURE_SIDEBAND_BYTES = 64 * 1024
MAX_PYTEST_FAILURE_IDENTITIES = 64
MAX_PYTEST_TEST_SOURCE_BYTES = 8 * 1024 * 1024
MAX_PYTEST_TEST_TOTAL_BYTES = 128 * 1024 * 1024
MAX_PYTEST_TEST_SOURCES = 4096
MAX_PYTEST_TEST_TREE_ENTRIES = 16_384
MAX_WINDOWS_PYTEST_PATH = 240
PYTEST_TEMP_PREFIX = "hsp-"
PYTEST_TEMP_NAME_BUDGET = 32
_WINDOWS_PYTEST_PROJECTED_SUFFIX = (
    "pytest-of-runner/pytest-123/test_committed_source_install_e0/checkout/"
    "runner-temp/hsconfig-runtime-3.11/Lib/site-packages/hsconfig/resources/"
    "runtime-contract.json"
)
PYTEST_FAILURE_SIDEBAND_NAME = "pytest-failure-identities.json"
GLOBAL_MINIMUM = 90.0
GLOBAL_TARGET = 95.0
_PYTEST_FAILURE_SIDEBAND_OPTION = "--hsconfig-failure-sideband"
# Keep diagnostic identities within one conventional filesystem-component budget.
MAX_SAFE_PYTEST_IDENTIFIER_LENGTH = 255
_SAFE_PYTEST_IDENTIFIER = re.compile(
    rf"[A-Za-z_][A-Za-z0-9_]{{0,{MAX_SAFE_PYTEST_IDENTIFIER_LENGTH - 1}}}"
)
_SAFE_PYTEST_TEST_PATH = re.compile(
    r"tests/(?:[A-Za-z0-9_][A-Za-z0-9_.-]*/)*"
    r"[A-Za-z0-9_][A-Za-z0-9_.-]*\.py"
)
_PYTEST_FAILURE_PHASES = frozenset({"setup", "call", "teardown"})
_PytestTestIdentity = tuple[str, str | None, str]
_RuntimeSourceInventoryEntry = tuple[str, str, str]
_RuntimeSourceInventory = tuple[_RuntimeSourceInventoryEntry, ...]
_COVERAGE_TEST_REPOSITORY_ROOT = "HSCONFIG_COVERAGE_TEST_REPOSITORY_ROOT"
_COVERAGE_TEST_REPOSITORY_BINDING = "HSCONFIG_COVERAGE_TEST_REPOSITORY_BINDING"
_LOCKED_TEST_RUNTIME_BINDING = "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING"
_LOCKED_TEST_RUNTIME_SHA256 = "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_SHA256"
_PYTEST_IMPORT_INVENTORY = "HSCONFIG_COVERAGE_PYTEST_IMPORT_INVENTORY"
_PYTEST_IMPORT_INVENTORY_SHA256 = (
    "HSCONFIG_COVERAGE_PYTEST_IMPORT_INVENTORY_SHA256"
)
_BOOTSTRAP_AUTHORITY_VARIABLES = {
    "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL",
    "HSCONFIG_RUNTIME_MANIFEST",
    "HSCONFIG_RUNTIME_MANIFEST_SHA256",
    _COVERAGE_TEST_REPOSITORY_ROOT,
    _COVERAGE_TEST_REPOSITORY_BINDING,
    _LOCKED_TEST_RUNTIME_BINDING,
    _LOCKED_TEST_RUNTIME_SHA256,
    _PYTEST_IMPORT_INVENTORY,
    _PYTEST_IMPORT_INVENTORY_SHA256,
}
_KNOWN_CHECKER_TRANSPORT_FAILURES = {
    "coverage checker stderr read failed",
    "coverage checker stdout read failed",
    "coverage checker timed out",
    "coverage checker stdout exceeded limit",
}
CRITICAL_MODULES = (
    "src/hsconfig/atomic_io.py",
    "src/hsconfig/output_publisher.py",
    "src/hsconfig/current_output.py",
    "src/hsconfig/runtime_installer.py",
    "src/hsconfig/runtime_state.py",
    "src/hsconfig/deck_config_ini.py",
    "src/hsconfig/apply_gate.py",
    "src/hsconfig/apply_decision.py",
    "src/hsconfig/operator_status.py",
)
CHECKER_BRIDGE = r"""
import json
import sys
from scripts.check_coverage_contract import CoverageDataError, check_coverage

def closed(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def reject(value):
    raise ValueError("non-finite JSON constant")

def empty(message):
    return {
        "passed": False,
        "global_branch_percent": None,
        "global_covered_branches": None,
        "global_num_branches": None,
        "global_minimum": 90.0,
        "target_met": False,
        "critical_modules": [],
        "errors": [message],
    }

try:
    source = sys.stdin.buffer.read(268435457)
    if len(source) > 268435456:
        raise ValueError("coverage input exceeds size limit")
    payload = json.loads(
        source,
        object_pairs_hook=closed,
        parse_constant=reject,
    )
    report = check_coverage(payload)
    report["global_covered_branches"] = payload["totals"]["covered_branches"]
    report["global_num_branches"] = payload["totals"]["num_branches"]
except (UnicodeError, json.JSONDecodeError, TypeError, ValueError, CoverageDataError):
    report = empty("malformed coverage data")
    code = 2
else:
    code = 0 if report["passed"] else 1
print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
raise SystemExit(code)
"""
_GATED_LAUNCHER = (
    "import json,os,subprocess,sys; header=bytearray(); "
    "[(header.extend(chunk),None)[1] for chunk in iter(lambda:os.read(0,1),b'\\n')]; "
    "argv=json.loads(header); "
    "assert isinstance(argv,list) and argv and all(isinstance(x,str) for x in argv); "
    "raise SystemExit(subprocess.run(argv,stdin=sys.stdin.buffer).returncode)"
)


class CoverageGateError(RuntimeError):
    pass


class RuntimeLockCategory(str, Enum):
    MANIFEST_BINDING = "manifest_binding"
    REPOSITORY_BINDING = "repository_binding"
    ARTIFACT_BINDING = "artifact_binding"
    DISTRIBUTION_SET = "distribution_set"
    DISTRIBUTION_VERSION = "distribution_version"
    DISTRIBUTION_ORIGIN = "distribution_origin"
    LOCAL_PROJECT_BINDING = "local_project_binding"
    RUNTIME_TREE_CLOSURE = "runtime_tree_closure"
    UNKNOWN = "unknown"


class RuntimeLockReason(str, Enum):
    GIT_HEAD_UNAVAILABLE = "git_head_unavailable"
    GIT_TREE_UNAVAILABLE = "git_tree_unavailable"
    GIT_STATUS_UNAVAILABLE = "git_status_unavailable"
    GIT_INDEX_UNAVAILABLE = "git_index_unavailable"
    REPOSITORY_LSTAT_UNAVAILABLE = "repository_lstat_unavailable"
    COMMIT_CHANGED = "commit_changed"
    TREE_CHANGED = "tree_changed"
    DIRTY_STATUS = "dirty_status"
    ROOT_DEVICE_CHANGED = "root_device_changed"
    ROOT_INODE_CHANGED = "root_inode_changed"
    ROOT_SIZE_CHANGED = "root_size_changed"
    ROOT_MTIME_CHANGED = "root_mtime_changed"
    ROOT_CTIME_CHANGED = "root_ctime_changed"
    ROOT_MODE_CHANGED = "root_mode_changed"


def _validate_runtime_lock_reason_pair(
    category: RuntimeLockCategory | None,
    reason: RuntimeLockReason | None,
    *,
    allow_unknown_category: bool,
) -> None:
    if reason is None:
        return
    if not isinstance(reason, RuntimeLockReason):
        raise TypeError("reason must be a RuntimeLockReason")
    allowed_categories = {RuntimeLockCategory.REPOSITORY_BINDING}
    if allow_unknown_category:
        allowed_categories.add(RuntimeLockCategory.UNKNOWN)
    if category not in allowed_categories:
        raise ValueError("runtime lock reason requires repository_binding category")


class RuntimeLockError(CoverageGateError):
    def __init__(
        self,
        message: str,
        *,
        category: RuntimeLockCategory | None = None,
        reason: RuntimeLockReason | None = None,
    ) -> None:
        if (
            reason is not None
            and category is not None
            and not isinstance(category, RuntimeLockCategory)
        ):
            raise TypeError("category must be a RuntimeLockCategory")
        effective_category = (
            category
            if isinstance(category, RuntimeLockCategory)
            else RuntimeLockCategory.UNKNOWN
        )
        _validate_runtime_lock_reason_pair(
            effective_category,
            reason,
            allow_unknown_category=True,
        )
        super().__init__(message)
        self.category = effective_category
        self.reason = reason


@contextmanager
def _runtime_lock_phase(category: RuntimeLockCategory) -> Iterator[None]:
    try:
        yield
    except RuntimeLockError as exc:
        if exc.category is not RuntimeLockCategory.UNKNOWN:
            raise
        raise RuntimeLockError(
            str(exc),
            category=category,
            reason=exc.reason,
        ) from exc


@contextmanager
def _runtime_repository_binding_phase(reason: RuntimeLockReason) -> Iterator[None]:
    try:
        yield
    except (CoverageGateError, OSError, UnicodeError) as exc:
        raise RuntimeLockError(
            "runtime repository binding is unavailable",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=reason,
        ) from exc


@dataclass(frozen=True)
class CoverageRun:
    run_root: Path
    run_identity: tuple[int, int]
    pytest_temp_root: Path
    pytest_temp_identity: tuple[int, int]
    coverage_data: Path
    coverage_json: Path
    failure_sideband: Path
    failure_sideband_identity: tuple[int, int]
    environment: dict[str, str]
    locked_test_runtime: _LockedTestRuntimeBinding | None


@dataclass(frozen=True)
class _CoverageRuntimeBinding:
    repository_root: Path
    commit_oid: str
    tree_oid: str
    root_identity: _PathIdentity
    pythonpath: tuple[Path, Path]
    source_inventory: _RuntimeSourceInventory
    build_backend_identity: _PathIdentity
    build_backend_inventory_sha256: str


@dataclass(frozen=True)
class CoverageReportIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    run_modified_ns: int
    run_changed_ns: int
    digest: str
    content: bytes = field(repr=False, compare=False)


@dataclass(frozen=True)
class _PathIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    mode: int


@dataclass(frozen=True)
class _LockedTestRuntimeBinding:
    source_root: Path
    source_inventory_sha256: str
    repository_root: Path
    commit_oid: str
    tree_oid: str
    root_identity: _PathIdentity
    build_backend_root: Path
    build_backend_identity: _PathIdentity
    build_backend_inventory_sha256: str
    environment_root: Path
    interpreter: Path
    interpreter_identity: _PathIdentity
    interpreter_sha256: str
    git_executable: Path
    git_identity: _PathIdentity
    git_sha256: str
    pwsh_executable: Path
    pwsh_identity: _PathIdentity
    pwsh_sha256: str


@dataclass(frozen=True)
class _CoverageScanRequest:
    source_root: Path
    repository: Path
    outputs_root: Path
    commit_oid: str
    tree_oid: str
    root_identity: _PathIdentity
    tree_mode: str
    build_distributions: bool


@dataclass(frozen=True)
class _BoundedResult:
    completed: subprocess.CompletedProcess[str]
    timed_out: bool
    stdout: _BoundedCapture
    stderr: _BoundedCapture


@dataclass(frozen=True)
class _PytestResult:
    returncode: int
    timed_out: bool


@dataclass(frozen=True)
class _PytestFailureSideband:
    status: _PytestFailureSidebandStatus
    identities: tuple[str, ...]
    truncated: bool


class _PytestFailureSidebandStatus(Enum):
    VALID = "valid"
    RECORDER_UNAVAILABLE = "recorder_unavailable"
    MISSING = "missing"
    INVALID_BINDING = "invalid_binding"
    INVALID_SCHEMA = "invalid_schema"
    IO_ERROR = "io_error"


@dataclass
class _PytestFailureState:
    repository_root: Path
    sideband: Path
    identities_by_nodeid: dict[str, dict[str, object] | None] = field(
        default_factory=dict
    )
    failures: list[dict[str, object]] = field(default_factory=list)
    truncated: bool = False
    unavailable: bool = False
    locked_runtime: _LockedTestRuntimeBinding | None = None
    locked_runtime_document: str | None = None
    locked_runtime_sha256: str | None = None
    import_inventory: _RuntimeSourceInventory | None = None
    import_finder: _BoundPytestImportFinder | None = None
    original_directory: Path | None = None
    pytest_tmpdir_module: ModuleType | None = None
    original_pytest_rmtree: Any = None
    bound_pytest_rmtree: Any = None
    displaced_pytest_rmtree: Any = None
    failure_reporter: Any = None
    collection_paths: frozenset[str] = frozenset()
    pytest_basetemp: Path | None = None
    pytest_basetemp_identity: tuple[int, int] | None = None
    pytest_basetemp_parent_identity: tuple[int, int] | None = None


_ACTIVE_PYTEST_FAILURE_STATE: _PytestFailureState | None = None
_PYTEST_FAILURE_STATE_KEY = StashKey[_PytestFailureState]()


@dataclass(frozen=True)
class _BoundPytestSecureRmtree:
    state: _PytestFailureState

    def __call__(
        self,
        path: str | os.PathLike[str],
        ignore_errors: bool = False,
    ) -> None:
        try:
            _pytest_secure_rmtree(self.state, path, ignore_errors=ignore_errors)
        except BaseException:
            self.state.unavailable = True
            raise


@dataclass(frozen=True)
class _BoundPytestFailureReporter:
    state: _PytestFailureState

    @hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item: Any, call: Any) -> Iterator[None]:
        del item, call
        outcome = yield
        _bind_pytest_cleanup_for_hook_chain(self.state)
        _record_pytest_failure(self.state, outcome.get_result())

    def pytest_collectreport(self, report: Any) -> None:
        _record_pytest_collection_failure(self.state, report)

    @hookimpl(hookwrapper=True, tryfirst=True)
    def pytest_sessionfinish(self, session: Any, exitstatus: int) -> Iterator[None]:
        del exitstatus
        if not _bind_pytest_cleanup_for_hook_chain(self.state):
            self.state.unavailable = True
            session.exitstatus = 2
        if self.state.unavailable:
            session.exitstatus = 2
        outcome = yield
        try:
            outcome.get_result()
        except BaseException:
            self.state.unavailable = True
            session.exitstatus = 2
            _write_pytest_failure_sideband(self.state)
            outcome.force_result(None)
        if not _pytest_cleanup_binding_intact(self.state):
            self.state.unavailable = True
            session.exitstatus = 2
        if (
            self.state.displaced_pytest_rmtree is not None
            and _pytest_cleanup_binding_intact(self.state)
        ):
            self.state.pytest_tmpdir_module.rmtree = (
                self.state.displaced_pytest_rmtree
            )
        _write_pytest_failure_sideband(self.state)


class _BoundedCapture:
    def __init__(self, limit: int = CAPTURE_LIMIT) -> None:
        self.limit = limit
        self.tail = bytearray()
        self.digest = hashlib.sha256()
        self.total = 0
        self.error: BaseException | None = None

    def drain(self, stream: Any) -> None:
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    return
                self.total += len(chunk)
                self.digest.update(chunk)
                self.tail.extend(chunk)
                if len(self.tail) > self.limit:
                    del self.tail[: len(self.tail) - self.limit]
        except (OSError, ValueError) as exc:
            self.error = exc

    @property
    def truncated(self) -> bool:
        return self.total > self.limit

    def text(self) -> str:
        return bytes(self.tail).decode("utf-8", errors="replace")


def _safe_pytest_item_identity(
    item: Any,
    repository_root: Path,
) -> dict[str, object] | None:
    try:
        item_path = Path(str(item.path)).resolve(strict=True)
        module_path = Path(str(item.module.__file__)).resolve(strict=True)
        if module_path != item_path:
            return None
        relative_path = item_path.relative_to(repository_root).as_posix()
    except (AttributeError, OSError, ValueError):
        return None
    if (
        len(relative_path) > 240
        or _SAFE_PYTEST_TEST_PATH.fullmatch(relative_path) is None
    ):
        return None
    original_name = getattr(item, "originalname", None)
    if original_name is None:
        original_name = str(getattr(item, "name", "")).split("[", 1)[0]
    if (
        not isinstance(original_name, str)
        or _SAFE_PYTEST_IDENTIFIER.fullmatch(original_name) is None
    ):
        return None
    item_class = getattr(item, "cls", None)
    class_name = None if item_class is None else getattr(item_class, "__name__", None)
    if class_name is not None and (
        not isinstance(class_name, str)
        or _SAFE_PYTEST_IDENTIFIER.fullmatch(class_name) is None
    ):
        return None
    return {
        "path": relative_path,
        "class": class_name,
        "function": original_name,
        "parameter": None,
    }


def _pytest_test_identity_allowlist(
    repository_root: Path,
    *,
    source_inventory: _RuntimeSourceInventory,
) -> frozenset[_PytestTestIdentity]:
    try:
        if not isinstance(source_inventory, tuple):
            raise CoverageGateError("pytest test identity source inventory is invalid")
        inventory_rows: list[_RuntimeSourceInventoryEntry] = []
        expected_sources: dict[str, tuple[str, str]] = {}
        seen_inventory_paths: set[str] = set()
        for row in source_inventory:
            if (
                not isinstance(row, tuple)
                or len(row) != 3
                or not all(isinstance(value, str) for value in row)
            ):
                raise CoverageGateError(
                    "pytest test identity source inventory is invalid"
                )
            relative, digest, git_mode = row
            parts = relative.split("/")
            if (
                not parts
                or not all(_is_canonical_repository_component(part) for part in parts)
                or relative in seen_inventory_paths
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or git_mode not in {"100644", "100755"}
            ):
                raise CoverageGateError(
                    "pytest test identity source inventory is invalid"
                )
            seen_inventory_paths.add(relative)
            inventory_rows.append(row)
            if relative.startswith("tests/") and relative.endswith(".py"):
                if (
                    len(relative) > 240
                    or _SAFE_PYTEST_TEST_PATH.fullmatch(relative) is None
                ):
                    raise CoverageGateError(
                        "pytest test identity source inventory is invalid"
                    )
                expected_sources[relative] = (digest, git_mode)
        if tuple(inventory_rows) != tuple(
            sorted(inventory_rows, key=lambda item: item[0])
        ):
            raise CoverageGateError("pytest test identity source inventory is invalid")
        root_metadata = repository_root.lstat()
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_ISLNK(root_metadata.st_mode)
            or _is_reparse(root_metadata)
        ):
            raise CoverageGateError("pytest test identity root is unsafe")
        root = repository_root.resolve(strict=True)
        tests_root = root / "tests"
        tests_metadata = tests_root.lstat()
        if (
            not stat.S_ISDIR(tests_metadata.st_mode)
            or stat.S_ISLNK(tests_metadata.st_mode)
            or _is_reparse(tests_metadata)
        ):
            raise CoverageGateError("pytest test identity tree is unsafe")
        pending = [tests_root]
        directory_identities: dict[Path, _PathIdentity] = {}
        sources: list[tuple[Path, str]] = []
        entries_seen = 0
        while pending:
            directory = pending.pop()
            directory_metadata = directory.lstat()
            if (
                not stat.S_ISDIR(directory_metadata.st_mode)
                or stat.S_ISLNK(directory_metadata.st_mode)
                or _is_reparse(directory_metadata)
            ):
                raise CoverageGateError("pytest test identity tree is unsafe")
            directory_identities[directory] = _identity(directory_metadata)
            with os.scandir(directory) as scanned:
                entries = sorted(scanned, key=lambda entry: entry.name)
            for entry in entries:
                entries_seen += 1
                if entries_seen > MAX_PYTEST_TEST_TREE_ENTRIES:
                    raise CoverageGateError("pytest test identity tree is too large")
                path = directory / entry.name
                metadata = path.lstat()
                if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                    raise CoverageGateError("pytest test identity tree is unsafe")
                resolved = path.resolve(strict=True)
                if root not in resolved.parents:
                    raise CoverageGateError("pytest test identity path escaped root")
                if stat.S_ISDIR(metadata.st_mode):
                    pending.append(path)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise CoverageGateError("pytest test identity tree is unsafe")
                if path.suffix != ".py":
                    continue
                if getattr(metadata, "st_nlink", 1) != 1:
                    raise CoverageGateError("pytest test identity source is unsafe")
                relative = resolved.relative_to(root).as_posix()
                if (
                    len(relative) > 240
                    or _SAFE_PYTEST_TEST_PATH.fullmatch(relative) is None
                    or len(sources) >= MAX_PYTEST_TEST_SOURCES
                ):
                    raise CoverageGateError("pytest test identity source is unsafe")
                sources.append((path, relative))
        if {relative for _path, relative in sources} != set(expected_sources):
            raise CoverageGateError("pytest test identity source inventory differs")
        identities: set[_PytestTestIdentity] = set()
        total_bytes = 0
        function_nodes = (ast.FunctionDef, ast.AsyncFunctionDef)
        for path, relative in sorted(sources, key=lambda row: row[1]):
            source, metadata = _read_bound_regular_file(
                path,
                maximum_bytes=MAX_PYTEST_TEST_SOURCE_BYTES,
                error_type=CoverageGateError,
                label="pytest test identity source",
            )
            if getattr(metadata, "st_nlink", 1) != 1:
                raise CoverageGateError("pytest test identity source is unsafe")
            expected_digest, expected_mode = expected_sources[relative]
            actual_mode = _runtime_git_mode(metadata.st_mode)
            if (
                hashlib.sha256(source).hexdigest() != expected_digest
                or (actual_mode is not None and actual_mode != expected_mode)
            ):
                raise CoverageGateError("pytest test identity source differs")
            total_bytes += len(source)
            if total_bytes > MAX_PYTEST_TEST_TOTAL_BYTES:
                raise CoverageGateError("pytest test identity sources are too large")
            module = ast.parse(source.decode("utf-8"), filename=relative)
            for node in module.body:
                if isinstance(node, function_nodes):
                    if node.name.startswith("test") and (
                        _SAFE_PYTEST_IDENTIFIER.fullmatch(node.name) is not None
                    ):
                        identities.add((relative, None, node.name))
                    continue
                if not isinstance(node, ast.ClassDef) or (
                    _SAFE_PYTEST_IDENTIFIER.fullmatch(node.name) is None
                ):
                    continue
                for child in node.body:
                    if (
                        isinstance(child, function_nodes)
                        and child.name.startswith("test")
                        and _SAFE_PYTEST_IDENTIFIER.fullmatch(child.name) is not None
                    ):
                        identities.add((relative, node.name, child.name))
        for directory, expected in directory_identities.items():
            if _identity(directory.lstat()) != expected:
                raise CoverageGateError("pytest test identity tree changed")
        if _identity(repository_root.lstat()) != _identity(root_metadata):
            raise CoverageGateError("pytest test identity root changed")
        if not identities:
            raise CoverageGateError("pytest test identity projection is empty")
        return frozenset(identities)
    except CoverageGateError:
        raise
    except (
        OSError,
        RuntimeLockError,
        UnicodeError,
        SyntaxError,
        RecursionError,
        TypeError,
        ValueError,
    ) as exc:
        raise CoverageGateError("pytest test identity projection failed") from exc


def _pytest_collection_path_allowlist(
    source_inventory: _RuntimeSourceInventory,
) -> frozenset[str]:
    if not isinstance(source_inventory, tuple):
        raise CoverageGateError("pytest collection source inventory is invalid")
    paths: set[str] = set()
    for row in source_inventory:
        if (
            not isinstance(row, tuple)
            or len(row) != 3
            or not all(isinstance(value, str) for value in row)
        ):
            raise CoverageGateError("pytest collection source inventory is invalid")
        path, digest, git_mode = row
        if (
            re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or git_mode not in {"100644", "100755"}
        ):
            raise CoverageGateError("pytest collection source inventory is invalid")
        if not (path.startswith("tests/") and path.endswith(".py")):
            continue
        if (
            len(path) > 240
            or _SAFE_PYTEST_TEST_PATH.fullmatch(path) is None
            or path in paths
        ):
            raise CoverageGateError("pytest collection source inventory is invalid")
        paths.add(path)
    if not paths:
        raise CoverageGateError("pytest collection source inventory is empty")
    return frozenset(paths)


_PYTEST_IMPORT_SOURCE_PATHS = (
    "src/hsconfig/__init__.py",
    "tests/__init__.py",
)


def _pytest_import_inventory_rows(
    inventory: _RuntimeSourceInventory,
) -> _RuntimeSourceInventory:
    if not isinstance(inventory, tuple):
        raise CoverageGateError("pytest import inventory is invalid")
    observed: dict[str, _RuntimeSourceInventoryEntry] = {}
    previous = ""
    for row in inventory:
        if (
            not isinstance(row, tuple)
            or len(row) != 3
            or not all(isinstance(value, str) for value in row)
        ):
            raise CoverageGateError("pytest import inventory is invalid")
        relative, digest, git_mode = row
        parts = relative.split("/")
        if (
            not parts
            or not all(_is_canonical_repository_component(part) for part in parts)
            or relative <= previous
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or git_mode not in {"100644", "100755"}
        ):
            raise CoverageGateError("pytest import inventory is invalid")
        previous = relative
        if relative in _PYTEST_IMPORT_SOURCE_PATHS:
            observed[relative] = row
    if set(observed) != set(_PYTEST_IMPORT_SOURCE_PATHS):
        raise CoverageGateError("pytest import inventory is incomplete")
    return inventory


def _pytest_import_inventory_document(
    inventory: _RuntimeSourceInventory,
) -> tuple[str, str]:
    rows = _pytest_import_inventory_rows(inventory)
    document = json.dumps(
        {
            "schema_version": 1,
            "sources": [
                {"path": path, "sha256": digest, "git_mode": git_mode}
                for path, digest, git_mode in rows
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return document, hashlib.sha256(document.encode("utf-8")).hexdigest()


def _pytest_import_inventory_binding(
    document: str,
    expected_sha256: str,
) -> _RuntimeSourceInventory:
    try:
        encoded = document.encode("utf-8")
        if (
            len(encoded) > 1024 * 1024
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
            or hashlib.sha256(encoded).hexdigest() != expected_sha256
        ):
            raise ValueError("pytest import inventory binding")
        payload = json.loads(
            encoded,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "sources",
        }:
            raise ValueError("pytest import inventory schema")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != 1
            or not isinstance(payload["sources"], list)
        ):
            raise ValueError("pytest import inventory schema")
        rows: list[_RuntimeSourceInventoryEntry] = []
        for source in payload["sources"]:
            if not isinstance(source, dict) or set(source) != {
                "path",
                "sha256",
                "git_mode",
            }:
                raise ValueError("pytest import inventory source")
            rows.append(
                (
                    source["path"],
                    source["sha256"],
                    source["git_mode"],
                )
            )
        return _pytest_import_inventory_rows(tuple(rows))
    except (json.JSONDecodeError, TypeError, UnicodeError, ValueError) as exc:
        raise CoverageGateError("pytest import inventory binding is invalid") from exc


def pytest_addoption(parser: Any) -> None:
    parser.getgroup("hsconfig coverage").addoption(
        _PYTEST_FAILURE_SIDEBAND_OPTION,
        action="store",
        default=None,
        help="controller-owned sanitized pytest failure identity sideband",
    )


def _pytest_failure_state(config: Any) -> _PytestFailureState | None:
    try:
        return config.stash.get(_PYTEST_FAILURE_STATE_KEY, None)
    except (AttributeError, TypeError):
        return _ACTIVE_PYTEST_FAILURE_STATE


def pytest_configure(config: Any) -> None:
    global _ACTIVE_PYTEST_FAILURE_STATE
    raw_sideband = config.getoption(_PYTEST_FAILURE_SIDEBAND_OPTION)
    if raw_sideband is None:
        return
    try:
        repository_root = Path(str(config.rootpath)).resolve(strict=True)
        sideband = Path(raw_sideband)
        if not sideband.is_absolute() or sideband.name != PYTEST_FAILURE_SIDEBAND_NAME:
            return
        sideband_parent = sideband.parent.resolve(strict=True)
        if sideband_parent == repository_root or repository_root in sideband_parent.parents:
            return
    except (OSError, TypeError, ValueError):
        return
    locked_runtime: _LockedTestRuntimeBinding | None = None
    raw_locked_runtime = os.environ.get(_LOCKED_TEST_RUNTIME_BINDING)
    raw_locked_runtime_sha256 = os.environ.get(_LOCKED_TEST_RUNTIME_SHA256)
    if raw_locked_runtime is not None or raw_locked_runtime_sha256 is not None:
        if raw_locked_runtime is None or raw_locked_runtime_sha256 is None:
            raise CoverageGateError("locked pytest runtime authority is incomplete")
        locked_runtime = _locked_test_runtime_binding(
            raw_locked_runtime,
            raw_locked_runtime_sha256,
        )
        if repository_root != locked_runtime.repository_root:
            raise CoverageGateError("locked pytest repository root differs")
    import_inventory: _RuntimeSourceInventory | None = None
    raw_import_inventory = os.environ.get(_PYTEST_IMPORT_INVENTORY)
    raw_import_inventory_sha256 = os.environ.get(_PYTEST_IMPORT_INVENTORY_SHA256)
    if raw_import_inventory is not None or raw_import_inventory_sha256 is not None:
        if raw_import_inventory is None or raw_import_inventory_sha256 is None:
            raise CoverageGateError("pytest import inventory authority is incomplete")
        import_inventory = _pytest_import_inventory_binding(
            raw_import_inventory,
            raw_import_inventory_sha256,
        )
    if (
        locked_runtime is None
        and repository_root != ROOT.resolve(strict=True)
        and import_inventory is None
    ):
        raise CoverageGateError("pytest import inventory authority is unavailable")
    state = _PytestFailureState(
        repository_root=repository_root,
        sideband=sideband,
        locked_runtime=locked_runtime,
        locked_runtime_document=raw_locked_runtime,
        locked_runtime_sha256=raw_locked_runtime_sha256,
        import_inventory=import_inventory,
        collection_paths=(
            frozenset()
            if import_inventory is None
            else _pytest_collection_path_allowlist(import_inventory)
        ),
    )
    reporter = _BoundPytestFailureReporter(state)
    bound_pytest_rmtree = _BoundPytestSecureRmtree(state)
    try:
        import _pytest.tmpdir as pytest_tmpdir

        original_pytest_rmtree = pytest_tmpdir.rmtree
        if isinstance(original_pytest_rmtree, _BoundPytestSecureRmtree):
            raise CoverageGateError("pytest temporary cleanup is already patched")
        state.pytest_tmpdir_module = pytest_tmpdir
        state.original_pytest_rmtree = original_pytest_rmtree
        state.bound_pytest_rmtree = bound_pytest_rmtree
        state.failure_reporter = reporter
        config.stash[_PYTEST_FAILURE_STATE_KEY] = state
        config.pluginmanager.register(reporter)
        _ACTIVE_PYTEST_FAILURE_STATE = state
        pytest_tmpdir.rmtree = bound_pytest_rmtree
    except BaseException:
        if state.failure_reporter is not None:
            try:
                config.pluginmanager.unregister(state.failure_reporter)
            except (AttributeError, KeyError, TypeError, ValueError):
                pass
        if (
            state.pytest_tmpdir_module is not None
            and state.original_pytest_rmtree is not None
            and state.pytest_tmpdir_module.rmtree is bound_pytest_rmtree
        ):
            state.pytest_tmpdir_module.rmtree = state.original_pytest_rmtree
        try:
            del config.stash[_PYTEST_FAILURE_STATE_KEY]
        except (AttributeError, KeyError, TypeError):
            pass
        _ACTIVE_PYTEST_FAILURE_STATE = None
        raise


def _bind_pytest_basetemp(session: Any, state: _PytestFailureState) -> None:
    try:
        factory = session.config._tmp_path_factory
        basetemp = Path(factory.getbasetemp())
        basetemp_metadata = basetemp.lstat()
        parent = basetemp.parent
        parent_metadata = parent.lstat()
        if (
            not basetemp.is_absolute()
            or basetemp.resolve(strict=True) != basetemp
            or not stat.S_ISDIR(basetemp_metadata.st_mode)
            or stat.S_ISLNK(basetemp_metadata.st_mode)
            or _is_reparse(basetemp_metadata)
            or parent.resolve(strict=True) != parent
            or not stat.S_ISDIR(parent_metadata.st_mode)
            or stat.S_ISLNK(parent_metadata.st_mode)
            or _is_reparse(parent_metadata)
        ):
            raise CoverageGateError("pytest temporary cleanup authority is unsafe")
    except (AttributeError, OSError, TypeError, ValueError) as exc:
        raise CoverageGateError(
            "pytest temporary cleanup authority is unavailable"
        ) from exc
    state.pytest_basetemp = basetemp
    state.pytest_basetemp_identity = (
        basetemp_metadata.st_dev,
        basetemp_metadata.st_ino,
    )
    state.pytest_basetemp_parent_identity = (
        parent_metadata.st_dev,
        parent_metadata.st_ino,
    )


def _pytest_cleanup_binding_intact(state: _PytestFailureState) -> bool:
    import sys as interpreter_sys

    bound = state.bound_pytest_rmtree
    module = state.pytest_tmpdir_module
    return (
        isinstance(bound, _BoundPytestSecureRmtree)
        and bound.state is state
        and module is interpreter_sys.modules.get("_pytest.tmpdir")
        and getattr(module, "rmtree", None) is bound
    )


def _bind_pytest_cleanup_for_hook_chain(state: _PytestFailureState) -> bool:
    import sys as interpreter_sys

    if _pytest_cleanup_binding_intact(state):
        return True
    module = state.pytest_tmpdir_module
    bound = state.bound_pytest_rmtree
    if (
        module is not interpreter_sys.modules.get("_pytest.tmpdir")
        or not isinstance(bound, _BoundPytestSecureRmtree)
        or bound.state is not state
    ):
        state.unavailable = True
        return False
    current = getattr(module, "rmtree", None)
    state.displaced_pytest_rmtree = current
    module.rmtree = bound
    state.unavailable = True
    return _pytest_cleanup_binding_intact(state)


def _pytest_secure_rmtree(
    state: _PytestFailureState,
    path: str | os.PathLike[str],
    ignore_errors: bool = False,
) -> None:
    del ignore_errors
    if (
        state.pytest_basetemp is None
        or state.pytest_basetemp_identity is None
        or state.pytest_basetemp_parent_identity is None
    ):
        raise CoverageGateError("pytest temporary cleanup authority is unavailable")
    candidate = Path(os.path.abspath(os.fspath(path)))
    basetemp = state.pytest_basetemp
    try:
        basetemp_metadata = basetemp.lstat()
    except FileNotFoundError:
        if candidate == basetemp:
            return
        raise CoverageGateError("pytest temporary cleanup authority was lost") from None
    except OSError as exc:
        raise CoverageGateError(
            "pytest temporary cleanup authority cannot be inspected"
        ) from exc
    if (
        (basetemp_metadata.st_dev, basetemp_metadata.st_ino)
        != state.pytest_basetemp_identity
        or basetemp.resolve(strict=True) != basetemp
        or not stat.S_ISDIR(basetemp_metadata.st_mode)
        or stat.S_ISLNK(basetemp_metadata.st_mode)
        or _is_reparse(basetemp_metadata)
    ):
        raise CoverageGateError("pytest temporary cleanup authority changed")
    if candidate == basetemp:
        temporary_root = basetemp.parent
        temporary_root_identity = state.pytest_basetemp_parent_identity
    elif candidate.parent == basetemp:
        temporary_root = basetemp
        temporary_root_identity = state.pytest_basetemp_identity
    else:
        raise CoverageGateError("pytest temporary cleanup escaped its authority")
    try:
        metadata = candidate.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise CoverageGateError("pytest temporary cleanup target cannot be inspected") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
    ):
        raise CoverageGateError("pytest temporary cleanup target is unsafe")
    _cleanup_owned_run_root(
        temporary_root,
        candidate,
        (metadata.st_dev, metadata.st_ino),
        expected_temporary_root_identity=temporary_root_identity,
    )


def _drop_pytest_import_modules() -> None:
    for name in tuple(sys.modules):
        if (
            name == "tests"
            or name.startswith("tests.")
            or name == "hsconfig"
            or name.startswith("hsconfig.")
        ):
            del sys.modules[name]


def _pytest_import_module_snapshot() -> dict[str, object]:
    return {
        name: module
        for name, module in sys.modules.items()
        if name == "tests"
        or name.startswith("tests.")
        or name == "hsconfig"
        or name.startswith("hsconfig.")
    }


class _BoundPytestImportAuthority:
    def __init__(
        self,
        *,
        product_root: Path,
        tests_root: Path,
        inventory: _RuntimeSourceInventory,
    ) -> None:
        self.inventory = _pytest_import_inventory_rows(inventory)
        self.entries = {
            relative: (digest, git_mode)
            for relative, digest, git_mode in self.inventory
        }
        self.roots = {
            "src/hsconfig": self._bind_root(product_root, "product"),
            "tests": self._bind_root(tests_root, "tests"),
        }

    @staticmethod
    def _bind_root(root: Path, label: str) -> tuple[Path, _PathIdentity]:
        try:
            resolved = root.resolve(strict=True)
            metadata = resolved.lstat()
        except OSError as exc:
            raise CoverageGateError(f"locked pytest {label} root is unavailable") from exc
        if (
            resolved != root
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
        ):
            raise CoverageGateError(f"locked pytest {label} root is unsafe")
        return resolved, _identity(metadata)

    def _binding(self, relative: str) -> tuple[str, Path, _PathIdentity, tuple[str, ...]]:
        for prefix, (root, identity) in self.roots.items():
            marker = f"{prefix}/"
            if relative.startswith(marker):
                suffix = tuple(relative[len(marker) :].split("/"))
                if not suffix or not all(
                    _is_canonical_repository_component(part) for part in suffix
                ):
                    break
                return prefix, root, identity, suffix
        raise CoverageGateError("locked pytest import path is outside authority")

    def read(self, relative: str) -> tuple[Path, bytes]:
        try:
            digest, git_mode = self.entries[relative]
            _prefix, root, root_identity, parts = self._binding(relative)
            root_before = root.lstat()
            if (
                _identity(root_before) != root_identity
                or root.resolve(strict=True) != root
                or not stat.S_ISDIR(root_before.st_mode)
                or stat.S_ISLNK(root_before.st_mode)
                or _is_reparse(root_before)
            ):
                raise CoverageGateError("locked pytest import root changed")
            path = _assert_runtime_path_ancestors(
                root,
                list(parts),
                label="pytest import source",
            )
            if path.resolve(strict=True) != path:
                raise CoverageGateError("locked pytest import path is unsafe")
            source, metadata = _read_bound_regular_file(
                path,
                maximum_bytes=MAX_PYTEST_TEST_SOURCE_BYTES,
                error_type=CoverageGateError,
                label="locked pytest import source",
            )
            root_after = root.lstat()
            actual_mode = _runtime_git_mode(metadata.st_mode)
            if (
                _identity(root_after) != root_identity
                or root.resolve(strict=True) != root
                or getattr(metadata, "st_nlink", 1) != 1
                or (actual_mode is not None and actual_mode != git_mode)
            ):
                raise CoverageGateError("locked pytest import source differs")
            if hashlib.sha256(source).hexdigest() == digest:
                return path, source
            if _windows_host():
                canonical_source = source.replace(b"\r\n", b"\n")
                if (
                    b"\r" not in canonical_source
                    and hashlib.sha256(canonical_source).hexdigest() == digest
                ):
                    return path, canonical_source
            raise CoverageGateError("locked pytest import source differs")
        except CoverageGateError:
            raise
        except (KeyError, OSError, RuntimeLockError, TypeError, ValueError) as exc:
            raise CoverageGateError("locked pytest import source is unavailable") from exc

    def is_file(self, relative: str) -> bool:
        return relative in self.entries

    def is_dir(self, relative: str) -> bool:
        marker = f"{relative.rstrip('/')}/"
        return any(path.startswith(marker) for path in self.entries)

    def children(self, relative: str) -> tuple[str, ...]:
        marker = f"{relative.rstrip('/')}/"
        return tuple(
            sorted(
                {
                    path[len(marker) :].split("/", 1)[0]
                    for path in self.entries
                    if path.startswith(marker)
                }
            )
        )

    def directory(self, relative: str) -> Path:
        if not self.is_dir(relative):
            raise CoverageGateError("locked pytest namespace is outside inventory")
        try:
            _prefix, root, root_identity, parts = self._binding(f"{relative}/member")
            root_before = root.lstat()
            if (
                _identity(root_before) != root_identity
                or root.resolve(strict=True) != root
            ):
                raise CoverageGateError("locked pytest namespace root changed")
            directory = _assert_runtime_path_ancestors(
                root,
                [*parts[:-1], "member"],
                label="pytest namespace",
            ).parent
            metadata = directory.lstat()
            root_after = root.lstat()
            if (
                directory.resolve(strict=True) != directory
                or not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or _is_reparse(metadata)
                or _identity(root_after) != root_identity
            ):
                raise CoverageGateError("locked pytest namespace is unsafe")
            return directory
        except CoverageGateError:
            raise
        except (OSError, RuntimeLockError, TypeError, ValueError) as exc:
            raise CoverageGateError("locked pytest namespace is unavailable") from exc

    def relative_for_path(self, path: Path) -> str:
        try:
            absolute = path.absolute()
            for prefix, (root, _identity_value) in self.roots.items():
                if absolute == root or root in absolute.parents:
                    suffix = absolute.relative_to(root).as_posix()
                    return f"{prefix}/{suffix}" if suffix else prefix
        except (OSError, ValueError):
            pass
        raise CoverageGateError("locked pytest loader path is outside authority")


class _BoundPytestTraversable(Traversable):
    def __init__(self, authority: _BoundPytestImportAuthority, relative: str) -> None:
        self._authority = authority
        self._relative = relative.rstrip("/")

    @property
    def name(self) -> str:
        return self._relative.rsplit("/", 1)[-1]

    def iterdir(self) -> Iterator[_BoundPytestTraversable]:
        if not self.is_dir():
            return iter(())
        return iter(
            self.joinpath(child) for child in self._authority.children(self._relative)
        )

    def is_dir(self) -> bool:
        return self._authority.is_dir(self._relative)

    def is_file(self) -> bool:
        return self._authority.is_file(self._relative)

    def joinpath(self, *descendants: str) -> _BoundPytestTraversable:
        parts: list[str] = []
        for descendant in descendants:
            parts.extend(str(descendant).replace("\\", "/").split("/"))
        if not parts or not all(
            _is_canonical_repository_component(part) for part in parts
        ):
            raise FileNotFoundError("invalid packaged resource path")
        return _BoundPytestTraversable(
            self._authority,
            "/".join((self._relative, *parts)),
        )

    def open(self, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if not self.is_file():
            raise FileNotFoundError(self._relative)
        if mode not in {"r", "rt", "rb"}:
            raise ValueError("packaged resources are read-only")
        if mode == "rb" and (args or kwargs):
            raise TypeError("binary packaged resources accept no open arguments")
        _path, payload = self._authority.read(self._relative)
        binary = io.BytesIO(payload)
        if mode == "rb":
            return binary
        encoding = kwargs.pop("encoding", "utf-8")
        errors = kwargs.pop("errors", "strict")
        newline = kwargs.pop("newline", None)
        if args or kwargs:
            raise TypeError("unsupported packaged resource open arguments")
        return io.TextIOWrapper(
            binary,
            encoding=encoding,
            errors=errors,
            newline=newline,
        )


class _BoundPytestResourceReader(TraversableResources):
    def __init__(self, authority: _BoundPytestImportAuthority, relative: str) -> None:
        self._authority = authority
        self._relative = relative

    def files(self) -> Traversable:
        return _BoundPytestTraversable(self._authority, self._relative)


class _BoundPytestSourceLoader(SourceFileLoader):
    def __init__(
        self,
        fullname: str,
        path: Path,
        source: bytes,
        *,
        authority: _BoundPytestImportAuthority,
        package_relative: str | None,
    ) -> None:
        super().__init__(fullname, str(path))
        self._bound_source = source
        self._authority = authority
        self._package_relative = package_relative

    def get_code(self, fullname: str) -> Any:
        if fullname != self.name:
            raise ImportError("locked pytest loader name differs")
        return compile(
            self._bound_source,
            self.path,
            "exec",
            dont_inherit=True,
        )

    def get_source(self, fullname: str) -> str:
        if fullname != self.name:
            raise ImportError("locked pytest loader name differs")
        return self._bound_source.decode("utf-8")

    def get_data(self, path: str) -> bytes:
        relative = self._authority.relative_for_path(Path(path))
        _bound_path, payload = self._authority.read(relative)
        return payload

    def get_resource_reader(self, fullname: str) -> TraversableResources | None:
        if fullname != self.name or self._package_relative is None:
            return None
        return _BoundPytestResourceReader(
            self._authority,
            self._package_relative,
        )


class _BoundPytestNamespaceLoader(importlib_abc.Loader):
    def __init__(
        self,
        authority: _BoundPytestImportAuthority,
        package_relative: str,
    ) -> None:
        self._authority = authority
        self._package_relative = package_relative

    def create_module(self, spec: ModuleSpec) -> None:
        del spec
        return None

    def exec_module(self, module: ModuleType) -> None:
        del module

    def get_resource_reader(self, fullname: str) -> TraversableResources:
        del fullname
        return _BoundPytestResourceReader(
            self._authority,
            self._package_relative,
        )


class _BoundPytestImportFinder(importlib_abc.MetaPathFinder):
    def __init__(
        self,
        authority: _BoundPytestImportAuthority,
        *,
        prior_modules: Mapping[str, object],
    ) -> None:
        self._authority = authority
        self.prior_modules = dict(prior_modules)

    def find_spec(
        self,
        fullname: str,
        path: object = None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        del path, target
        if fullname == "hsconfig":
            prefix = "src/hsconfig"
            suffix = ""
        elif fullname.startswith("hsconfig."):
            prefix = "src/hsconfig"
            suffix = fullname.removeprefix("hsconfig.").replace(".", "/")
        elif fullname == "tests":
            prefix = "tests"
            suffix = ""
        elif fullname.startswith("tests."):
            prefix = "tests"
            suffix = fullname.removeprefix("tests.").replace(".", "/")
        else:
            return None
        package_relative = f"{prefix}/{suffix}/__init__.py" if suffix else f"{prefix}/__init__.py"
        module_relative = f"{prefix}/{suffix}.py" if suffix else ""
        candidates = [
            (package_relative, True),
            (module_relative, False),
        ]
        selected = [
            (relative, is_package)
            for relative, is_package in candidates
            if relative and self._authority.is_file(relative)
        ]
        namespace_relative = f"{prefix}/{suffix}" if suffix else prefix
        if not selected and self._authority.is_dir(namespace_relative):
            namespace_path = self._authority.directory(namespace_relative)
            namespace_loader = _BoundPytestNamespaceLoader(
                self._authority,
                namespace_relative,
            )
            namespace_spec = ModuleSpec(
                fullname,
                namespace_loader,
                origin=str(namespace_path),
                is_package=True,
            )
            namespace_spec.submodule_search_locations = [str(namespace_path)]
            return namespace_spec
        if len(selected) != 1:
            raise CoverageGateError("locked pytest submodule is outside inventory")
        relative, is_package = selected[0]
        module_path, source = self._authority.read(relative)
        package_root = relative.removesuffix("/__init__.py") if is_package else None
        loader = _BoundPytestSourceLoader(
            fullname,
            module_path,
            source,
            authority=self._authority,
            package_relative=package_root,
        )
        spec = ModuleSpec(
            fullname,
            loader,
            origin=str(module_path),
            is_package=is_package,
        )
        spec.has_location = True
        if is_package:
            spec.submodule_search_locations = [str(module_path.parent)]
        return spec


def _bound_package_module(
    name: str,
    initializer: Path,
    source: bytes,
    *,
    authority: _BoundPytestImportAuthority,
    package_relative: str,
) -> ModuleType:
    loader = _BoundPytestSourceLoader(
        name,
        initializer,
        source,
        authority=authority,
        package_relative=package_relative,
    )
    spec = ModuleSpec(name, loader, origin=str(initializer), is_package=True)
    spec.has_location = True
    spec.submodule_search_locations = [str(initializer.parent)]
    module = ModuleType(name)
    module.__file__ = str(initializer)
    module.__loader__ = loader
    module.__package__ = name
    module.__path__ = [str(initializer.parent)]
    module.__spec__ = spec
    return module


def _bind_pytest_import_roots(
    repository_root: Path,
    *,
    source_inventory: _RuntimeSourceInventory,
) -> _BoundPytestImportFinder:
    inventory = _pytest_import_inventory_rows(source_inventory)
    snapshot = _pytest_import_module_snapshot()
    meta_path_snapshot = tuple(sys.meta_path)
    try:
        product_root = ROOT.resolve(strict=True) / "src" / "hsconfig"
        tests_root = repository_root.resolve(strict=True) / "tests"
        authority = _BoundPytestImportAuthority(
            product_root=product_root,
            tests_root=tests_root,
            inventory=inventory,
        )
        product_init, product_source = authority.read("src/hsconfig/__init__.py")
        tests_init, tests_source = authority.read("tests/__init__.py")
        finder = _BoundPytestImportFinder(
            authority,
            prior_modules=snapshot,
        )
        product_module = _bound_package_module(
            "hsconfig",
            product_init,
            product_source,
            authority=authority,
            package_relative="src/hsconfig",
        )
        tests_module = _bound_package_module(
            "tests",
            tests_init,
            tests_source,
            authority=authority,
            package_relative="tests",
        )
        sys.meta_path.insert(0, finder)
        _drop_pytest_import_modules()
        sys.modules["hsconfig"] = product_module
        sys.modules["tests"] = tests_module
        product_module.__loader__.exec_module(product_module)
        tests_module.__loader__.exec_module(tests_module)
        return finder
    except BaseException:
        sys.meta_path[:] = meta_path_snapshot
        _drop_pytest_import_modules()
        sys.modules.update(snapshot)
        raise


def pytest_sessionstart(session: Any) -> None:
    state = _pytest_failure_state(session.config)
    if state is None:
        return
    if not _pytest_cleanup_binding_intact(state):
        state.unavailable = True
        raise CoverageGateError("pytest temporary cleanup binding differs")
    _bind_pytest_basetemp(session, state)
    if state.locked_runtime is None:
        if state.repository_root != ROOT.resolve(strict=True):
            if state.import_inventory is None:
                raise CoverageGateError("pytest import inventory authority is unavailable")
            state.import_finder = _bind_pytest_import_roots(
                state.repository_root,
                source_inventory=state.import_inventory,
            )
        return
    binding = state.locked_runtime
    startup_directory = Path.cwd().resolve(strict=True)
    if startup_directory != binding.repository_root:
        raise CoverageGateError("locked pytest repository working directory differs")
    validated_inventory = _assert_locked_test_runtime(binding)
    selected_inventory = _pytest_import_inventory_rows(validated_inventory)
    selected_collection_paths = _pytest_collection_path_allowlist(
        validated_inventory
    )
    if (
        state.import_inventory is not None
        and state.import_inventory != selected_inventory
    ):
        raise CoverageGateError("pytest import inventory authority differs")
    if state.collection_paths and state.collection_paths != selected_collection_paths:
        raise CoverageGateError("pytest collection authority differs")
    state.collection_paths = selected_collection_paths
    state.import_finder = _bind_pytest_import_roots(
        binding.repository_root,
        source_inventory=validated_inventory,
    )
    state.original_directory = binding.source_root


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    state = _pytest_failure_state(config)
    if state is None:
        return
    parameter_groups: dict[tuple[str, str | None, str], list[str]] = {}
    for item in items:
        identity = _safe_pytest_item_identity(item, state.repository_root)
        if identity is None and state.locked_runtime is not None:
            raise CoverageGateError("locked pytest item provenance differs")
        nodeid = getattr(item, "nodeid", None)
        if not isinstance(nodeid, str) or nodeid in state.identities_by_nodeid:
            if state.locked_runtime is not None:
                raise CoverageGateError("locked pytest item identity differs")
            state.unavailable = True
            continue
        state.identities_by_nodeid[nodeid] = identity
        if identity is None or not hasattr(item, "callspec"):
            continue
        key = (
            str(identity["path"]),
            identity["class"] if isinstance(identity["class"], str) else None,
            str(identity["function"]),
        )
        parameter_groups.setdefault(key, []).append(nodeid)
    for nodeids in parameter_groups.values():
        total = len(nodeids)
        for ordinal, nodeid in enumerate(nodeids, start=1):
            identity = state.identities_by_nodeid[nodeid]
            if identity is not None:
                identity["parameter"] = {"ordinal": ordinal, "total": total}
    if state.locked_runtime is not None:
        if (
            state.original_directory is None
            or Path.cwd().resolve(strict=True)
            != state.locked_runtime.repository_root
        ):
            raise CoverageGateError("locked pytest collection working directory differs")


def _record_pytest_failure(state: _PytestFailureState | None, report: Any) -> None:
    if state is None or not bool(getattr(report, "failed", False)):
        return
    nodeid = getattr(report, "nodeid", None)
    phase = getattr(report, "when", None)
    identity = (
        state.identities_by_nodeid.get(nodeid)
        if isinstance(nodeid, str)
        else None
    )
    if identity is None or phase not in _PYTEST_FAILURE_PHASES:
        state.unavailable = True
        return
    failure = dict(identity)
    failure["phase"] = phase
    if len(state.failures) < MAX_PYTEST_FAILURE_IDENTITIES:
        state.failures.append(failure)
    else:
        state.truncated = True


def _record_pytest_collection_failure(
    state: _PytestFailureState | None,
    report: Any,
) -> None:
    if state is None or not bool(getattr(report, "failed", False)):
        return
    path = getattr(report, "nodeid", None)
    if (
        not isinstance(path, str)
        or len(path) > 240
        or _SAFE_PYTEST_TEST_PATH.fullmatch(path) is None
        or path not in state.collection_paths
    ):
        state.unavailable = True
        return
    failure: dict[str, object] = {"path": path, "phase": "collection"}
    if failure in state.failures:
        return
    if len(state.failures) < MAX_PYTEST_FAILURE_IDENTITIES:
        state.failures.append(failure)
    else:
        state.truncated = True


def _write_pytest_failure_sideband(state: _PytestFailureState) -> None:
    failures = [] if state.unavailable else state.failures
    truncated = False if state.unavailable else state.truncated
    document = {
        "schema_version": 1,
        "recorder_status": (
            "unavailable" if state.unavailable else "available"
        ),
        "failures": failures,
        "truncated": truncated,
    }
    source = (
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if len(source) > MAX_PYTEST_FAILURE_SIDEBAND_BYTES:
        return
    descriptor: int | None = None
    try:
        parent = state.sideband.parent.lstat()
        before = state.sideband.lstat()
        if (
            not stat.S_ISDIR(parent.st_mode)
            or stat.S_ISLNK(parent.st_mode)
            or _is_reparse(parent)
            or not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or _is_reparse(before)
            or getattr(before, "st_nlink", 1) != 1
        ):
            return
        flags = os.O_WRONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(state.sideband, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or getattr(opened, "st_nlink", 1) != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            return
        os.ftruncate(descriptor, 0)
        offset = 0
        while offset < len(source):
            written = os.write(descriptor, source[offset:])
            if written <= 0:
                return
            offset += written
        os.fsync(descriptor)
    except (OSError, TypeError, ValueError):
        return
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    del exitstatus
    state = _pytest_failure_state(session.config)
    if state is None:
        return
    if state.locked_runtime is not None:
        try:
            _assert_locked_test_runtime(state.locked_runtime)
        except (AssertionError, CoverageGateError, OSError, RuntimeLockError):
            state.unavailable = True
            session.exitstatus = 2
        finally:
            if state.original_directory is not None:
                try:
                    os.chdir(state.original_directory)
                except OSError:
                    state.unavailable = True
                    session.exitstatus = 2
    _write_pytest_failure_sideband(state)


def pytest_unconfigure(config: Any) -> None:
    global _ACTIVE_PYTEST_FAILURE_STATE
    state = _pytest_failure_state(config)
    if state is not None and state.pytest_tmpdir_module is not None:
        current = getattr(state.pytest_tmpdir_module, "rmtree", None)
        if current is state.bound_pytest_rmtree:
            state.pytest_tmpdir_module.rmtree = state.original_pytest_rmtree
        elif current is not state.original_pytest_rmtree:
            state.unavailable = True
            _write_pytest_failure_sideband(state)
    if state is not None and state.import_finder is not None:
        import_finder = state.import_finder
        _drop_pytest_import_modules()
        sys.modules.update(import_finder.prior_modules)
    if state is not None and state.original_directory is not None:
        try:
            os.chdir(state.original_directory)
        except OSError:
            pass
    if state is not None and state.failure_reporter is not None:
        try:
            config.pluginmanager.unregister(state.failure_reporter)
        except (AttributeError, KeyError, TypeError, ValueError):
            pass
    try:
        del config.stash[_PYTEST_FAILURE_STATE_KEY]
    except (AttributeError, KeyError, TypeError):
        pass
    _ACTIVE_PYTEST_FAILURE_STATE = None


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


def _enable_posix_subreaper() -> None:
    if sys.platform != "linux":
        return
    import ctypes

    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise CoverageGateError("coverage subprocess subreaper setup failed")


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
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

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
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise CoverageGateError("coverage subprocess isolation failed")
        information = ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = 0x00002000
        if not kernel32.SetInformationJobObject(
            job,
            9,
            ctypes.byref(information),
            ctypes.sizeof(information),
        ) or not kernel32.AssignProcessToJobObject(
            job,
            wintypes.HANDLE(int(self.process._handle)),  # noqa: SLF001
        ):
            kernel32.CloseHandle(job)
            try:
                self.process.kill()
            except OSError:
                pass
            raise CoverageGateError("coverage subprocess isolation failed")
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
            except ProcessLookupError:
                pass
            except OSError:
                if self.process.poll() is None:
                    self.process.kill()
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
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=30)


def _failure_report(
    message: str,
    returncode: int,
    *,
    runtime_lock_category: RuntimeLockCategory | None = None,
    runtime_lock_reason: RuntimeLockReason | None = None,
) -> dict[str, object]:
    _validate_runtime_lock_reason_pair(
        runtime_lock_category,
        runtime_lock_reason,
        allow_unknown_category=False,
    )
    report: dict[str, object] = {
        "passed": False,
        "global_branch_percent": None,
        "global_covered_branches": None,
        "global_num_branches": None,
        "global_minimum": GLOBAL_MINIMUM,
        "target_met": False,
        "critical_modules": [],
        "errors": [message],
        "returncode": returncode,
    }
    if runtime_lock_category is not None:
        report["runtime_lock_category"] = runtime_lock_category.value
    if runtime_lock_reason is not None:
        report["runtime_lock_reason"] = runtime_lock_reason.value
    return report


def _json_line(document: Mapping[str, object]) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def _emit_failure(
    message: str,
    returncode: int,
    *,
    runtime_lock_category: RuntimeLockCategory | None = None,
    runtime_lock_reason: RuntimeLockReason | None = None,
) -> None:
    sys.stdout.write(
        _json_line(
            _failure_report(
                message,
                returncode,
                runtime_lock_category=runtime_lock_category,
                runtime_lock_reason=runtime_lock_reason,
            )
        )
    )


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError("duplicate JSON key")
        document[key] = value
    return document


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _load_checker_json(output: str) -> dict[str, object]:
    try:
        document = json.loads(
            output,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise CoverageGateError("coverage checker emitted invalid JSON") from exc
    if not isinstance(document, dict):
        raise CoverageGateError("coverage checker emitted invalid JSON")
    return document


def _is_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _validate_checker_document(document: dict[str, object], returncode: int) -> None:
    if set(document) != {
        "passed",
        "global_branch_percent",
        "global_covered_branches",
        "global_num_branches",
        "global_minimum",
        "target_met",
        "critical_modules",
        "errors",
    }:
        raise CoverageGateError("coverage checker emitted invalid JSON")
    passed = document["passed"]
    target_met = document["target_met"]
    minimum = document["global_minimum"]
    percent = document["global_branch_percent"]
    covered_branches = document["global_covered_branches"]
    num_branches = document["global_num_branches"]
    errors = document["errors"]
    rows = document["critical_modules"]
    if (
        not isinstance(passed, bool)
        or not isinstance(target_met, bool)
        or not _is_number(minimum)
        or float(minimum) != GLOBAL_MINIMUM
        or not isinstance(errors, list)
        or any(not isinstance(error, str) or not error for error in errors)
        or not isinstance(rows, list)
    ):
        raise CoverageGateError("coverage checker emitted invalid JSON")
    if percent is not None and (
        not _is_number(percent) or not 0.0 <= float(percent) <= 100.0
    ):
        raise CoverageGateError("coverage checker emitted invalid JSON")
    if returncode in {0, 1}:
        if (
            isinstance(covered_branches, bool)
            or not isinstance(covered_branches, int)
            or isinstance(num_branches, bool)
            or not isinstance(num_branches, int)
            or covered_branches < 0
            or num_branches <= 0
            or covered_branches > num_branches
        ):
            raise CoverageGateError("coverage checker emitted invalid JSON")
        expected_percent = round(covered_branches * 100.0 / num_branches, 2)
        if float(percent) != expected_percent or target_met is not (
            covered_branches * 100 >= int(GLOBAL_TARGET) * num_branches
        ):
            raise CoverageGateError("coverage checker emitted contradictory JSON")
    elif covered_branches is not None or num_branches is not None:
        raise CoverageGateError("coverage checker emitted invalid JSON")
    if passed is not (returncode == 0):
        raise CoverageGateError("coverage checker result contradicted its exit status")
    if returncode in {0, 1}:
        if percent is None or len(rows) != len(CRITICAL_MODULES):
            raise CoverageGateError("coverage checker emitted invalid JSON")
        for expected_module, row in zip(CRITICAL_MODULES, rows, strict=True):
            if not isinstance(row, dict) or set(row) != {
                "module",
                "statement_percent",
                "branch_percent",
                "missing_lines",
                "missing_branches",
            }:
                raise CoverageGateError("coverage checker emitted invalid JSON")
            if row["module"] != expected_module:
                raise CoverageGateError("coverage checker emitted invalid JSON")
            statement = row["statement_percent"]
            branch = row["branch_percent"]
            missing_lines = row["missing_lines"]
            missing_branches = row["missing_branches"]
            if (
                statement is not None
                and (not _is_number(statement) or not 0 <= float(statement) <= 100)
            ) or (
                branch is not None
                and (not _is_number(branch) or not 0 <= float(branch) <= 100)
            ):
                raise CoverageGateError("coverage checker emitted invalid JSON")
            if (
                not isinstance(missing_lines, list)
                or any(
                    isinstance(line, bool) or not isinstance(line, int) or line < 1
                    for line in missing_lines
                )
                or not isinstance(missing_branches, list)
                or any(
                    not isinstance(pair, list)
                    or len(pair) != 2
                    or any(isinstance(line, bool) or not isinstance(line, int) for line in pair)
                    for pair in missing_branches
                )
            ):
                raise CoverageGateError("coverage checker emitted invalid JSON")
            if (statement is None) is not (branch is None):
                raise CoverageGateError("coverage checker emitted contradictory JSON")
            if statement is None and (missing_lines or missing_branches):
                raise CoverageGateError("coverage checker emitted contradictory JSON")
            if statement is not None and (
                (float(statement) == 100.0) is not (not missing_lines)
                or (float(branch) == 100.0) is not (not missing_branches)
            ):
                raise CoverageGateError("coverage checker emitted contradictory JSON")
        contract_failed = covered_branches * 100 < int(GLOBAL_MINIMUM) * num_branches or any(
            row["statement_percent"] != 100.0
            or row["branch_percent"] != 100.0
            or row["missing_lines"]
            or row["missing_branches"]
            for row in rows
        )
        if passed is contract_failed or bool(errors) is not contract_failed:
            raise CoverageGateError("coverage checker emitted invalid JSON")
    elif rows or percent is not None or not errors:
        raise CoverageGateError("coverage checker emitted invalid JSON")


def _portable_child_returncode(returncode: int) -> int:
    return returncode if returncode in {0, 1} else 2


def _forward_checker_result(result: subprocess.CompletedProcess[str]) -> int:
    if result.stderr:
        diagnostic = result.stderr.encode("utf-8", errors="replace")
        print(
            "coverage checker diagnostic "
            f"bytes={len(diagnostic)} sha256={hashlib.sha256(diagnostic).hexdigest()} "
            "truncated=false",
            file=sys.stderr,
        )
    wrapper_returncode = _portable_child_returncode(result.returncode)
    transport_failure: str | None = None
    try:
        document = _load_checker_json(result.stdout or "")
        embedded_returncode = document.pop("returncode", None)
        if embedded_returncode is not None:
            errors = document.get("errors")
            if (
                result.returncode != 2
                or embedded_returncode != 2
                or not isinstance(errors, list)
                or len(errors) != 1
                or errors[0] not in _KNOWN_CHECKER_TRANSPORT_FAILURES
            ):
                raise CoverageGateError("coverage checker emitted invalid JSON")
            transport_failure = errors[0]
        _validate_checker_document(document, wrapper_returncode)
    except CoverageGateError as exc:
        if "contradicted" in str(exc):
            _emit_failure("coverage checker result contradicted its exit status", 2)
        else:
            _emit_failure("coverage checker emitted invalid JSON", 2)
        return 2
    if result.returncode not in {0, 1}:
        if transport_failure is not None:
            document["returncode"] = 2
            sys.stdout.write(_json_line(document))
            return 2
        _emit_failure("coverage checker execution failed", 2)
        return 2
    document["returncode"] = wrapper_returncode
    sys.stdout.write(_json_line(document))
    return wrapper_returncode


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _process_tree_gate_interpreter(fallback: str | Path) -> str:
    if os.name != "nt":
        return str(fallback)
    raw_base = getattr(sys, "_base_executable", None)
    if not isinstance(raw_base, str) or not raw_base:
        raise CoverageGateError("process gate interpreter is invalid")
    candidate = Path(raw_base)
    if not candidate.is_absolute():
        raise CoverageGateError("process gate interpreter is invalid")
    try:
        metadata = candidate.lstat()
        canonical = candidate.resolve(strict=True)
        canonical_metadata = canonical.lstat()
    except (OSError, RuntimeError) as exc:
        raise CoverageGateError("process gate interpreter is invalid") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(canonical_metadata.st_mode)
        or _is_reparse(canonical_metadata)
        or not stat.S_ISREG(canonical_metadata.st_mode)
    ):
        raise CoverageGateError("process gate interpreter is invalid")
    return str(canonical)


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _identity(metadata: os.stat_result) -> _PathIdentity:
    return _PathIdentity(
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
    )


def _read_bound_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    error_type: type[CoverageGateError],
    label: str,
) -> tuple[bytes, os.stat_result]:
    try:
        parent_before = path.parent.lstat()
        path_before = path.lstat()
        if (
            not stat.S_ISDIR(parent_before.st_mode)
            or stat.S_ISLNK(parent_before.st_mode)
            or _is_reparse(parent_before)
            or not stat.S_ISREG(path_before.st_mode)
            or stat.S_ISLNK(path_before.st_mode)
            or _is_reparse(path_before)
            or getattr(path_before, "st_nlink", 1) not in {0, 1}
            or path_before.st_size > maximum_bytes
        ):
            raise error_type(f"{label} is unsafe")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or getattr(opened, "st_nlink", 1) not in {0, 1}
                or (opened.st_dev, opened.st_ino) != (path_before.st_dev, path_before.st_ino)
            ):
                raise error_type(f"{label} changed during read")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, maximum_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > maximum_bytes:
                    raise error_type(f"{label} exceeds size limit")
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        parent_after = path.parent.lstat()
        path_after = path.lstat()
    except CoverageGateError:
        raise
    except OSError as exc:
        raise error_type(f"{label} cannot be read") from exc
    if (
        _identity(after) != _identity(opened)
        or _identity(path_after) != _identity(path_before)
        or _identity(parent_after) != _identity(parent_before)
        or total != opened.st_size
    ):
        raise error_type(f"{label} changed during read")
    return b"".join(chunks), opened


def _locked_versions(lock_file: Path) -> dict[str, tuple[str, str]]:
    source, _ = _read_bound_regular_file(
        lock_file,
        maximum_bytes=MAX_LOCK_BYTES,
        error_type=RuntimeLockError,
        label="project lock",
    )
    try:
        document = tomllib.loads(source.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise RuntimeLockError("project lock cannot be read") from exc
    packages = document.get("packages")
    if not isinstance(packages, list) or not packages:
        raise RuntimeLockError("project lock package set is invalid")
    locked: dict[str, tuple[str, str]] = {}
    for row in packages:
        if not isinstance(row, dict):
            raise RuntimeLockError("project lock package row is invalid")
        name = row.get("name")
        version = row.get("version")
        wheels = row.get("wheels")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
            or not isinstance(wheels, list)
            or not wheels
        ):
            raise RuntimeLockError("project lock package identity is invalid")
        for wheel in wheels:
            if (
                not isinstance(wheel, dict)
                or not isinstance(wheel.get("url"), str)
                or not wheel["url"]
                or not isinstance(wheel.get("hashes"), dict)
                or not isinstance(wheel["hashes"].get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", wheel["hashes"]["sha256"])
            ):
                raise RuntimeLockError("project lock artifact identity is invalid")
        normalized = _normalized_name(name)
        if normalized in locked:
            raise RuntimeLockError("project lock contains duplicate package identity")
        locked[normalized] = (name, version)
    return locked


def _locked_wheels(lock_file: Path) -> dict[str, set[tuple[str, str]]]:
    source, _ = _read_bound_regular_file(
        lock_file,
        maximum_bytes=MAX_LOCK_BYTES,
        error_type=RuntimeLockError,
        label="project lock",
    )
    try:
        packages = tomllib.loads(source.decode("utf-8"))["packages"]
    except (UnicodeError, tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise RuntimeLockError("project lock cannot be read") from exc
    result: dict[str, set[tuple[str, str]]] = {}
    for package in packages:
        try:
            normalized = _normalized_name(package["name"])
            candidates = {
                (wheel["url"], wheel["hashes"]["sha256"])
                for wheel in package["wheels"]
            }
        except (KeyError, TypeError) as exc:
            raise RuntimeLockError("project lock artifact identity is invalid") from exc
        if not candidates or any(
            not isinstance(url, str)
            or not url
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            for url, digest in candidates
        ):
            raise RuntimeLockError("project lock artifact identity is invalid")
        result[normalized] = candidates
    return result


def _wheel_inventory(source: bytes) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > 100_000:
                raise RuntimeLockError("runtime wheel inventory is invalid")
            seen: set[str] = set()
            for info in infos:
                name = info.filename.replace("\\", "/")
                parts = name.split("/")
                unix_mode = (info.external_attr >> 16) & 0o170000
                if info.is_dir():
                    continue
                if (
                    name in seen
                    or name.startswith("/")
                    or any(part in {"", ".", ".."} for part in parts)
                    or info.file_size > MAX_RUNTIME_ARTIFACT_BYTES
                    or unix_mode not in {0, stat.S_IFREG}
                ):
                    raise RuntimeLockError("runtime wheel inventory is invalid")
                seen.add(name)
                payload = archive.read(info)
                rows.append(
                    {
                        "path": name,
                        "size": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise RuntimeLockError("runtime wheel inventory is invalid") from exc
    return sorted(rows, key=lambda row: str(row["path"]))


def _source_inventory_digest(inventory: object) -> str:
    encoded = json.dumps(
        inventory,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _runtime_git_mode(mode: int) -> str | None:
    if sys.platform == "win32":
        return None
    materialized = stat.S_IMODE(mode)
    if materialized == 0o644:
        return "100644"
    if materialized == 0o755:
        return "100755"
    raise RuntimeLockError("runtime bootstrap source mode is noncanonical")


def _assert_runtime_path_ancestors(
    root: Path,
    parts: list[str],
    *,
    label: str,
) -> Path:
    current = root
    try:
        for part in parts[:-1]:
            current = current / part
            metadata = current.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or _is_reparse(metadata)
                or current.resolve(strict=True) != current
            ):
                raise RuntimeLockError(f"{label} is unsafe")
    except RuntimeLockError:
        raise
    except OSError as exc:
        raise RuntimeLockError(f"{label} is unsafe") from exc
    return root.joinpath(*parts)


def _runtime_regular_tree(root: Path, *, label: str) -> list[Path]:
    try:
        root_metadata = root.lstat()
        if (
            not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_ISLNK(root_metadata.st_mode)
            or _is_reparse(root_metadata)
            or root.resolve(strict=True) != root
        ):
            raise RuntimeLockError(f"{label} is unsafe")
        pending = [root]
        files: list[Path] = []
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in sorted(entries, key=lambda item: item.name):
                    path = Path(entry.path)
                    metadata = path.lstat()
                    if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                        raise RuntimeLockError(f"{label} is unsafe")
                    if stat.S_ISDIR(metadata.st_mode):
                        if path.resolve(strict=True) != path:
                            raise RuntimeLockError(f"{label} is unsafe")
                        pending.append(path)
                        continue
                    if (
                        not stat.S_ISREG(metadata.st_mode)
                        or getattr(metadata, "st_nlink", 1) not in {0, 1}
                        or path.resolve(strict=True) != path
                    ):
                        raise RuntimeLockError(f"{label} is unsafe")
                    files.append(path)
    except RuntimeLockError:
        raise
    except OSError as exc:
        raise RuntimeLockError(f"{label} is unsafe") from exc
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def _runtime_startup_surface_policy(name: object, version: object) -> tuple[bool, tuple[str, ...]]:
    key = (_normalized_name(str(name)), str(version))
    hooks = {
        ("setuptools", "83.0.0"): ("distutils-precedence.pth",),
        ("coverage", "7.15.2"): ("a1_coverage.pth",),
    }.get(key, ())
    return not hooks, hooks


def _validate_runtime_source_inventory(
    document: Mapping[str, object],
    manifest_path: Path,
) -> tuple[str, _RuntimeSourceInventory]:
    raw_inventory = document.get("source_inventory")
    inventory_sha256 = document.get("source_inventory_sha256")
    local = document.get("local_project")
    if (
        not isinstance(raw_inventory, list)
        or not isinstance(inventory_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", inventory_sha256) is None
        or not isinstance(local, dict)
        or local.get("source_inventory_sha256") != inventory_sha256
    ):
        raise RuntimeLockError("runtime bootstrap source inventory is invalid")
    source_root_candidate = manifest_path.parent / "committed-source"
    try:
        root_metadata = source_root_candidate.lstat()
        source_root = source_root_candidate.resolve(strict=True)
    except OSError as exc:
        raise RuntimeLockError("runtime bootstrap source inventory is invalid") from exc
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or _is_reparse(root_metadata)
        or source_root != source_root_candidate
    ):
        raise RuntimeLockError("runtime bootstrap source inventory is invalid")
    inventory: list[dict[str, str]] = []
    expected_paths: set[str] = set()
    for row in raw_inventory:
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "sha256", "git_mode"}
            or not isinstance(row.get("path"), str)
            or row.get("git_mode") not in {"100644", "100755"}
            or re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256"))) is None
        ):
            raise RuntimeLockError("runtime bootstrap source inventory is invalid")
        relative = str(row["path"])
        parts = relative.split("/")
        if (
            not parts
            or not all(_is_canonical_repository_component(part) for part in parts)
            or relative in expected_paths
        ):
            raise RuntimeLockError("runtime bootstrap source inventory is invalid")
        expected_paths.add(relative)
        path = _assert_runtime_path_ancestors(
            source_root,
            parts,
            label="runtime bootstrap committed source",
        )
        try:
            payload, metadata = _read_bound_regular_file(
                path,
                maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
                error_type=RuntimeLockError,
                label="runtime bootstrap committed source",
            )
        except OSError as exc:
            raise RuntimeLockError("runtime bootstrap source inventory is invalid") from exc
        if (
            source_root not in path.resolve(strict=True).parents
            or hashlib.sha256(payload).hexdigest() != row["sha256"]
            or (
                (actual_mode := _runtime_git_mode(metadata.st_mode)) is not None
                and actual_mode != row["git_mode"]
            )
        ):
            raise RuntimeLockError("runtime bootstrap source inventory differs")
        inventory.append(dict(row))
    observed_paths = {
        path.relative_to(source_root).as_posix()
        for path in _runtime_regular_tree(
            source_root,
            label="runtime bootstrap source inventory",
        )
    }
    if (
        inventory != sorted(inventory, key=lambda row: row["path"])
        or observed_paths != expected_paths
        or _source_inventory_digest(inventory) != inventory_sha256
    ):
        raise RuntimeLockError("runtime bootstrap source inventory differs")
    bound_inventory = tuple(
        (row["path"], row["sha256"], row["git_mode"]) for row in inventory
    )
    return inventory_sha256, bound_inventory


def _validate_runtime_overlay(
    artifacts: list[dict[str, object]],
    build_backend_root: Path,
) -> tuple[_PathIdentity, str]:
    expected: dict[str, tuple[int, str]] = {}
    for artifact in artifacts:
        if artifact["install"] is not False:
            continue
        omitted = set(artifact["allowed_startup_surfaces"])
        for row in artifact["files"]:
            if not isinstance(row, dict) or set(row) != {"path", "size", "sha256"}:
                raise RuntimeLockError("runtime bootstrap overlay inventory is invalid")
            relative = row.get("path")
            size = row.get("size")
            digest = row.get("sha256")
            if (
                not isinstance(relative, str)
                or not isinstance(size, int)
                or size < 0
                or re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None
            ):
                raise RuntimeLockError("runtime bootstrap overlay inventory is invalid")
            parts = relative.split("/")
            if not parts or not all(
                _is_canonical_repository_component(part) for part in parts
            ):
                raise RuntimeLockError("runtime bootstrap overlay inventory is invalid")
            if relative in omitted:
                continue
            if relative in expected:
                raise RuntimeLockError("runtime bootstrap overlay paths collide")
            expected[relative] = (size, str(digest))
    try:
        root_before = build_backend_root.lstat()
    except OSError as exc:
        raise RuntimeLockError("runtime bootstrap overlay root is unavailable") from exc
    if (
        not stat.S_ISDIR(root_before.st_mode)
        or stat.S_ISLNK(root_before.st_mode)
        or _is_reparse(root_before)
    ):
        raise RuntimeLockError("runtime bootstrap overlay root is unsafe")
    observed: dict[str, tuple[int, str]] = {}
    rows: list[dict[str, object]] = []
    for path in _runtime_regular_tree(
        build_backend_root,
        label="runtime bootstrap overlay",
    ):
        payload, _ = _read_bound_regular_file(
            path,
            maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
            error_type=RuntimeLockError,
            label="runtime bootstrap overlay payload",
        )
        relative = path.relative_to(build_backend_root).as_posix()
        digest = hashlib.sha256(payload).hexdigest()
        observed[relative] = (
            len(payload),
            digest,
        )
        rows.append({"path": relative, "size": len(payload), "sha256": digest})
    try:
        root_after = build_backend_root.lstat()
    except OSError as exc:
        raise RuntimeLockError("runtime bootstrap overlay root is unavailable") from exc
    if observed != expected:
        raise RuntimeLockError("runtime bootstrap overlay inventory differs")
    if _identity(root_after) != _identity(root_before):
        raise RuntimeLockError("runtime bootstrap overlay root changed")
    return _identity(root_before), _runtime_inventory_digest(rows)


def _load_runtime_manifest(
    lock_file: Path,
    locked: Mapping[str, tuple[str, str]],
) -> dict[str, dict[str, object]] | None:
    try:
        if lock_file.resolve(strict=True) != LOCK_FILE.resolve(strict=True):
            return None
    except OSError:
        return None
    manifest_name = os.environ.get("HSCONFIG_RUNTIME_MANIFEST", "")
    expected_manifest_digest = os.environ.get("HSCONFIG_RUNTIME_MANIFEST_SHA256", "")
    sentinel = os.environ.get("HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL", "")
    if (
        not manifest_name
        or re.fullmatch(r"[0-9a-f]{64}", expected_manifest_digest) is None
        or re.fullmatch(r"[0-9a-f]{64}", sentinel) is None
    ):
        raise RuntimeLockError(
            "runtime bootstrap manifest is missing",
            category=RuntimeLockCategory.MANIFEST_BINDING,
        )
    manifest_path = Path(manifest_name)
    with _runtime_lock_phase(RuntimeLockCategory.MANIFEST_BINDING):
        source, _ = _read_bound_regular_file(
            manifest_path,
            maximum_bytes=MAX_RUNTIME_MANIFEST_BYTES,
            error_type=RuntimeLockError,
            label="runtime bootstrap manifest",
        )
    if hashlib.sha256(source).hexdigest() != expected_manifest_digest:
        raise RuntimeLockError(
            "runtime bootstrap manifest digest differs",
            category=RuntimeLockCategory.MANIFEST_BINDING,
        )
    try:
        document = json.loads(source, object_pairs_hook=_closed_object)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeLockError(
            "runtime bootstrap manifest is invalid",
            category=RuntimeLockCategory.MANIFEST_BINDING,
        ) from exc
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
        raise RuntimeLockError(
            "runtime bootstrap manifest is invalid",
            category=RuntimeLockCategory.MANIFEST_BINDING,
        )
    with _runtime_lock_phase(RuntimeLockCategory.ARTIFACT_BINDING):
        lock_source, _ = _read_bound_regular_file(
            lock_file,
            maximum_bytes=MAX_LOCK_BYTES,
            error_type=RuntimeLockError,
            label="project lock",
        )
    try:
        repository_candidate = Path(document["repository"])
        repository_metadata = repository_candidate.lstat()
        repository_root = repository_candidate.resolve(strict=True)
        repository_root_identity = _identity(repository_metadata)
        environment_root = Path(document["environment_root"]).resolve(strict=True)
        build_backend_candidate = Path(document["build_backend_root"])
        build_backend_metadata = build_backend_candidate.lstat()
        build_backend_root = build_backend_candidate.resolve(strict=True)
    except (OSError, TypeError) as exc:
        raise RuntimeLockError(
            "runtime bootstrap manifest is invalid",
            category=RuntimeLockCategory.MANIFEST_BINDING,
        ) from exc
    if (
        not stat.S_ISDIR(repository_metadata.st_mode)
        or stat.S_ISLNK(repository_metadata.st_mode)
        or _is_reparse(repository_metadata)
        or str(repository_root) != document["repository"]
        or not stat.S_ISDIR(build_backend_metadata.st_mode)
        or stat.S_ISLNK(build_backend_metadata.st_mode)
        or _is_reparse(build_backend_metadata)
        or build_backend_root != manifest_path.parent.resolve(strict=True) / "build-backend"
    ):
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.MANIFEST_BINDING,
        )
    with _runtime_lock_phase(RuntimeLockCategory.MANIFEST_BINDING):
        source_inventory_sha256, source_inventory = _validate_runtime_source_inventory(
            document, manifest_path
        )
    with _runtime_repository_binding_phase(
        RuntimeLockReason.GIT_HEAD_UNAVAILABLE
    ):
        head = _bound_git_oid("HEAD", repository=repository_root)
    with _runtime_repository_binding_phase(
        RuntimeLockReason.GIT_TREE_UNAVAILABLE
    ):
        tree = _bound_git_oid("HEAD^{tree}", repository=repository_root)
    with _runtime_repository_binding_phase(
        RuntimeLockReason.GIT_STATUS_UNAVAILABLE
    ):
        status = _bound_git_output(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            maximum_bytes=1024 * 1024,
            repository=repository_root,
        )
    with _runtime_repository_binding_phase(
        RuntimeLockReason.GIT_INDEX_UNAVAILABLE
    ):
        _assert_default_git_index(repository=repository_root)
    with _runtime_repository_binding_phase(
        RuntimeLockReason.REPOSITORY_LSTAT_UNAVAILABLE
    ):
        repository_after = repository_root.lstat()
    if (
        document["schema_version"] != 1
        or document["python_minor"] != f"{sys.version_info.major}.{sys.version_info.minor}"
        or environment_root != Path(sys.prefix).resolve(strict=True)
        or document["lock_sha256"] != hashlib.sha256(lock_source).hexdigest()
        or document["sentinel_sha256"] != hashlib.sha256(sentinel.encode("ascii")).hexdigest()
        or re.fullmatch(r"[0-9a-f]{40}", str(document["commit_oid"])) is None
        or re.fullmatch(r"[0-9a-f]{40}", str(document["tree_oid"])) is None
    ):
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.MANIFEST_BINDING,
        )
    repository_after_identity = _identity(repository_after)
    if document["commit_oid"] != head:
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.COMMIT_CHANGED,
        )
    if document["tree_oid"] != tree:
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.TREE_CHANGED,
        )
    if status != b"":
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.DIRTY_STATUS,
        )
    if repository_after_identity.device != repository_root_identity.device:
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.ROOT_DEVICE_CHANGED,
        )
    if repository_after_identity.inode != repository_root_identity.inode:
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.ROOT_INODE_CHANGED,
        )
    if repository_after_identity.size != repository_root_identity.size:
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.ROOT_SIZE_CHANGED,
        )
    if repository_after_identity.modified_ns != repository_root_identity.modified_ns:
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.ROOT_MTIME_CHANGED,
        )
    if repository_after_identity.changed_ns != repository_root_identity.changed_ns:
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.ROOT_CTIME_CHANGED,
        )
    if repository_after_identity.mode != repository_root_identity.mode:
        raise RuntimeLockError(
            "runtime bootstrap manifest binding differs",
            category=RuntimeLockCategory.REPOSITORY_BINDING,
            reason=RuntimeLockReason.ROOT_MODE_CHANGED,
        )
    with _runtime_lock_phase(RuntimeLockCategory.ARTIFACT_BINDING):
        candidates = _locked_wheels(lock_file)
    artifacts = document["artifacts"]
    local = document["local_project"]
    if not isinstance(artifacts, list) or len(artifacts) != len(locked) or not isinstance(local, dict):
        raise RuntimeLockError(
            "runtime bootstrap artifact set is invalid",
            category=RuntimeLockCategory.ARTIFACT_BINDING,
        )
    bound: dict[str, dict[str, object]] = {}
    for row in (*artifacts, local):
        expected_row_keys = (
            {"name", "version", "wheel_path", "sha256", "files", "source_inventory_sha256"}
            if row is local
            else {
                "name",
                "version",
                "url",
                "wheel_path",
                "sha256",
                "files",
                "install",
                "allowed_startup_surfaces",
            }
        )
        if not isinstance(row, dict) or set(row) != expected_row_keys:
            raise RuntimeLockError(
                "runtime bootstrap artifact row is invalid",
                category=RuntimeLockCategory.ARTIFACT_BINDING,
            )
        name = row.get("name")
        version = row.get("version")
        digest = row.get("sha256")
        if not isinstance(name, str) or not isinstance(version, str) or not isinstance(digest, str):
            raise RuntimeLockError(
                "runtime bootstrap artifact row is invalid",
                category=RuntimeLockCategory.ARTIFACT_BINDING,
            )
        normalized = _normalized_name(name)
        if normalized in bound or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise RuntimeLockError(
                "runtime bootstrap artifact row is invalid",
                category=RuntimeLockCategory.ARTIFACT_BINDING,
            )
        if normalized == "hsconfig":
            if (
                version != str(document.get("local_project", {}).get("version"))
                or row.get("source_inventory_sha256") != source_inventory_sha256
            ):
                raise RuntimeLockError(
                    "runtime bootstrap local artifact differs",
                    category=RuntimeLockCategory.ARTIFACT_BINDING,
                )
        else:
            if normalized not in locked or locked[normalized][1] != version:
                raise RuntimeLockError(
                    "runtime bootstrap artifact differs from project lock",
                    category=RuntimeLockCategory.ARTIFACT_BINDING,
                )
            url = row.get("url")
            if not isinstance(url, str) or (url, digest) not in candidates[normalized]:
                raise RuntimeLockError(
                    "runtime bootstrap artifact differs from project lock",
                    category=RuntimeLockCategory.ARTIFACT_BINDING,
                )
            install, allowed_startup_surfaces = _runtime_startup_surface_policy(name, version)
            if (
                row.get("install") is not install
                or row.get("allowed_startup_surfaces") != list(allowed_startup_surfaces)
            ):
                raise RuntimeLockError(
                    "runtime bootstrap artifact policy differs",
                    category=RuntimeLockCategory.ARTIFACT_BINDING,
                )
        wheel_path = Path(str(row.get("wheel_path", "")))
        try:
            wheel_resolved = wheel_path.resolve(strict=True)
            bootstrap_root = manifest_path.parent.resolve(strict=True)
        except OSError as exc:
            raise RuntimeLockError(
                "runtime bootstrap wheel path is invalid",
                category=RuntimeLockCategory.ARTIFACT_BINDING,
            ) from exc
        if bootstrap_root not in wheel_resolved.parents or ROOT in wheel_resolved.parents:
            raise RuntimeLockError(
                "runtime bootstrap wheel path is invalid",
                category=RuntimeLockCategory.ARTIFACT_BINDING,
            )
        with _runtime_lock_phase(RuntimeLockCategory.ARTIFACT_BINDING):
            wheel_source, _ = _read_bound_regular_file(
                wheel_path,
                maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
                error_type=RuntimeLockError,
                label="runtime bootstrap wheel",
            )
            wheel_inventory = _wheel_inventory(wheel_source)
        if (
            hashlib.sha256(wheel_source).hexdigest() != digest
            or row.get("files") != wheel_inventory
        ):
            raise RuntimeLockError(
                "runtime bootstrap wheel inventory differs",
                category=RuntimeLockCategory.ARTIFACT_BINDING,
            )
        copied = dict(row)
        copied["_wheel_source"] = wheel_source
        if normalized == "hsconfig":
            copied["_commit_oid"] = str(document["commit_oid"])
            copied["_tree_oid"] = str(document["tree_oid"])
            copied["_repository_root"] = repository_root
            copied["_repository_root_identity"] = repository_root_identity
            copied["_source_inventory"] = source_inventory
        elif copied["install"] is False:
            copied["_runtime_root"] = build_backend_root
        bound[normalized] = copied
    if set(bound) != set(locked) | {"hsconfig"}:
        raise RuntimeLockError(
            "runtime bootstrap artifact set differs",
            category=RuntimeLockCategory.ARTIFACT_BINDING,
        )
    with _runtime_lock_phase(RuntimeLockCategory.ARTIFACT_BINDING):
        build_backend_identity, build_backend_inventory_sha256 = (
            _validate_runtime_overlay(artifacts, build_backend_root)
        )
    bound["hsconfig"]["_build_backend_identity"] = build_backend_identity
    bound["hsconfig"]["_build_backend_inventory_sha256"] = (
        build_backend_inventory_sha256
    )
    return bound


def _distribution_text(distribution: Any, filename: str) -> str | None:
    try:
        value = distribution.read_text(filename)
    except (AttributeError, OSError):
        return None
    return value if isinstance(value, str) else None


def _wheel_installed_paths(
    artifact: Mapping[str, object],
    root: Path,
) -> set[str]:
    result: set[str] = set()
    for row in artifact["files"]:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise RuntimeLockError("runtime bootstrap wheel inventory is invalid")
        wheel_path = row["path"]
        parts = wheel_path.split("/")
        data_positions = [index for index, part in enumerate(parts) if part.endswith(".data")]
        if not data_positions:
            installed = root.joinpath(*parts)
        elif len(data_positions) == 1 and data_positions[0] + 2 <= len(parts):
            position = data_positions[0]
            scheme = parts[position + 1]
            scheme_root = sysconfig.get_paths().get(scheme)
            if scheme_root is None:
                raise RuntimeLockError("runtime wheel install scheme is invalid")
            installed = Path(scheme_root).joinpath(*parts[position + 2 :])
        else:
            raise RuntimeLockError("runtime wheel install path is invalid")
        result.add(os.path.relpath(installed, root).replace("\\", "/"))
    return result


def _entry_point_script_paths(artifact: Mapping[str, object], root: Path) -> set[str]:
    source = artifact.get("_wheel_source")
    if not isinstance(source, bytes):
        return set()
    names: set[str] = set()
    console_names: set[str] = set()
    try:
        artifact_name = artifact["name"]
        artifact_version = artifact["version"]
        if not isinstance(artifact_name, str) or not isinstance(artifact_version, str):
            raise RuntimeLockError("runtime wheel entry point authority is invalid")
        inventory = _wheel_inventory(source)
        if artifact.get("files") != inventory:
            raise RuntimeLockError("runtime wheel entry point inventory is unbound")
        inventory_paths = [str(row["path"]) for row in inventory]
        if len(inventory_paths) != len({path.casefold() for path in inventory_paths}):
            raise RuntimeLockError("runtime wheel entry point inventory is ambiguous")
        normalized_name = re.sub(r"[^A-Za-z0-9.]+", "_", artifact_name)
        normalized_version = re.sub(r"[^A-Za-z0-9.]+", "_", artifact_version)
        if not normalized_name or not normalized_version:
            raise RuntimeLockError("runtime wheel entry point authority is invalid")
        expected_dist_info = f"{normalized_name}-{normalized_version}.dist-info"
        top_level_dist_info = {
            path.split("/", 1)[0]
            for path in inventory_paths
            if path.split("/", 1)[0].endswith(".dist-info")
        }
        if (
            top_level_dist_info != {expected_dist_info}
            or f"{expected_dist_info}/RECORD" not in inventory_paths
        ):
            raise RuntimeLockError("runtime wheel entry point authority is invalid")
        entry_points_path = f"{expected_dist_info}/entry_points.txt"
        with zipfile.ZipFile(io.BytesIO(source)) as archive:
            if entry_points_path in inventory_paths:
                section = ""
                for raw in archive.read(entry_points_path).decode("utf-8").splitlines():
                    line = raw.strip()
                    if line.startswith("[") and line.endswith("]"):
                        section = line[1:-1].strip()
                    elif section in {"console_scripts", "gui_scripts"} and "=" in line:
                        name = line.split("=", 1)[0].strip()
                        if re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None:
                            raise RuntimeLockError("runtime wheel entry point is invalid")
                        names.add(name)
                        if section == "console_scripts":
                            console_names.add(name)
    except (KeyError, TypeError, UnicodeError, zipfile.BadZipFile) as exc:
        raise RuntimeLockError("runtime wheel entry points are invalid") from exc
    scripts = Path(sysconfig.get_paths()["scripts"])
    suffixes = (".exe", "-script.py") if os.name == "nt" else ("",)
    result = {
        os.path.relpath(scripts / f"{name}{suffix}", root).replace("\\", "/")
        for name in names
        for suffix in suffixes
    }
    if (
        isinstance(artifact_name, str)
        and _normalized_name(artifact_name) == "pip"
        and "pip3" in console_names
    ):
        launcher_suffix = ".exe" if os.name == "nt" else ""
        versioned_launcher = (
            f"pip{sys.version_info.major}.{sys.version_info.minor}{launcher_suffix}"
        )
        result.add(
            os.path.relpath(scripts / versioned_launcher, root).replace("\\", "/")
        )
    return result


def _bound_git_output(
    *arguments: str,
    maximum_bytes: int,
    repository: Path | None = None,
) -> bytes:
    repository_root = ROOT if repository is None else repository
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    platform_options: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process: subprocess.Popen[bytes] | None = None
    lease: _ProcessTreeLease | None = None
    stdout = bytearray()
    stderr = bytearray()
    overflow = threading.Event()
    errors: list[BaseException] = []

    def drain(stream: Any, target: bytearray, limit: int) -> None:
        try:
            while not overflow.is_set():
                remaining = limit - len(target)
                chunk = stream.read(min(8192, remaining + 1))
                if not chunk:
                    return
                if len(chunk) > remaining:
                    overflow.set()
                    return
                target.extend(chunk)
        except (OSError, ValueError) as exc:
            errors.append(exc)

    if os.name != "nt":
        _enable_posix_subreaper()
    baseline = _linux_direct_children()
    threads: list[threading.Thread] = []
    try:
        process = subprocess.Popen(
            (
                "git",
                "--no-replace-objects",
                "-C",
                str(repository_root),
                *arguments,
            ),
            cwd=repository_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            **platform_options,
        )
        lease = _ProcessTreeLease(process, baseline)
        if process.stdout is None or process.stderr is None:
            raise RuntimeLockError("local project repository pipes are unavailable")
        threads = [
            threading.Thread(
                target=drain,
                args=(process.stdout, stdout, maximum_bytes),
                daemon=True,
            ),
            threading.Thread(
                target=drain,
                args=(process.stderr, stderr, CAPTURE_LIMIT),
                daemon=True,
            ),
        ]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + 30.0
        while process.poll() is None and not overflow.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                overflow.set()
                break
            try:
                process.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                continue
        lease.terminate_remaining()
        for thread in threads:
            thread.join(timeout=30)
        if any(thread.is_alive() for thread in threads):
            raise RuntimeLockError("local project repository transport did not close")
    except (CoverageGateError, OSError, subprocess.TimeoutExpired) as exc:
        if lease is not None:
            lease.terminate_remaining()
        elif process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=30)
        raise RuntimeLockError("local project repository binding is unavailable") from exc
    finally:
        if process is not None:
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
    if process is None or process.returncode != 0 or overflow.is_set() or errors:
        raise RuntimeLockError("local project repository binding is unavailable")
    return bytes(stdout)


_WINDOWS_RESERVED_COMPONENTS = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
    *(f"com{index}" for index in "¹²³"),
    *(f"lpt{index}" for index in "¹²³"),
}


def _is_canonical_repository_component(component: str) -> bool:
    device_stem = component.split(".", 1)[0].casefold()
    return (
        component not in {"", ".", ".."}
        and not component.endswith((" ", "."))
        and not any(character in '<>:"/\\|?*' for character in component)
        and not any(ord(character) < 32 or ord(character) == 127 for character in component)
        and device_stem not in _WINDOWS_RESERVED_COMPONENTS
    )


def _bound_git_oid(revision: str, *, repository: Path | None = None) -> str:
    for attempt in range(2):
        try:
            source = _bound_git_output(
                "rev-parse",
                revision,
                maximum_bytes=64,
                repository=repository,
            )
            break
        except RuntimeLockError:
            if attempt == 1:
                raise
    if re.fullmatch(rb"[0-9a-f]{40}\n", source) is None:
        raise RuntimeLockError("local project repository identity is invalid")
    return source[:-1].decode("ascii")


def _assert_default_git_index(*, repository: Path | None = None) -> None:
    source = _bound_git_output(
        "ls-files",
        "-v",
        "-z",
        "--full-name",
        maximum_bytes=64 * 1024 * 1024,
        repository=repository,
    )
    if not source or not source.endswith(b"\0"):
        raise RuntimeLockError("local project repository index is invalid")
    seen: set[str] = set()
    folded: set[str] = set()
    for raw in source[:-1].split(b"\0"):
        if not raw.startswith(b"H "):
            raise RuntimeLockError("local project repository index has non-default flags")
        try:
            repository_path = raw[2:].decode("utf-8")
        except UnicodeError as exc:
            raise RuntimeLockError("local project repository index is invalid") from exc
        parts = repository_path.split("/")
        folded_path = repository_path.casefold()
        if (
            not all(_is_canonical_repository_component(part) for part in parts)
            or repository_path in seen
            or folded_path in folded
        ):
            raise RuntimeLockError("local project repository index is invalid")
        seen.add(repository_path)
        folded.add(folded_path)


def _local_repository_oids(artifact: Mapping[str, object] | None) -> tuple[str, str]:
    if artifact is None:
        raise RuntimeLockError("local project repository binding is missing")
    commit_oid = artifact.get("_commit_oid")
    tree_oid = artifact.get("_tree_oid")
    if (
        not isinstance(commit_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", commit_oid) is None
        or not isinstance(tree_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", tree_oid) is None
    ):
        raise RuntimeLockError("local project repository binding is invalid")
    return commit_oid, tree_oid


def _local_repository_root(artifact: Mapping[str, object] | None) -> Path:
    if artifact is None:
        raise RuntimeLockError("local project repository binding is missing")
    candidate = artifact.get("_repository_root")
    if not isinstance(candidate, Path):
        raise RuntimeLockError("local project repository binding is invalid")
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise RuntimeLockError("local project repository binding is invalid") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or resolved != candidate
    ):
        raise RuntimeLockError("local project repository binding is invalid")
    return resolved


def _local_repository_root_identity(
    artifact: Mapping[str, object] | None,
) -> _PathIdentity:
    if artifact is None:
        raise RuntimeLockError("local project repository binding is missing")
    identity = artifact.get("_repository_root_identity")
    if not isinstance(identity, _PathIdentity):
        raise RuntimeLockError("local project repository binding is invalid")
    return identity


def _committed_local_tree(
    artifact: Mapping[str, object] | None,
) -> dict[str, str]:
    _commit_oid, tree_oid = _local_repository_oids(artifact)
    repository = _local_repository_root(artifact)
    source = _bound_git_output(
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        tree_oid,
        "--",
        "src/hsconfig",
        maximum_bytes=64 * 1024 * 1024,
        repository=repository,
    )
    if not source or not source.endswith(b"\0"):
        raise RuntimeLockError("local project committed tree is invalid")
    result: dict[str, str] = {}
    folded: set[str] = set()
    for raw in source[:-1].split(b"\0"):
        try:
            metadata, raw_path = raw.split(b"\t", 1)
            mode, object_type, raw_oid = metadata.split(b" ")
            repository_path = raw_path.decode("utf-8")
            oid = raw_oid.decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise RuntimeLockError("local project committed tree is invalid") from exc
        prefix = "src/hsconfig/"
        if not repository_path.startswith(prefix):
            raise RuntimeLockError("local project committed tree path is invalid")
        relative = repository_path[len("src/") :]
        parts = relative.split("/")
        folded_path = relative.casefold()
        if (
            mode not in {b"100644", b"100755"}
            or object_type != b"blob"
            or re.fullmatch(r"[0-9a-f]{40}", oid) is None
            or len(parts) < 2
            or parts[0] != "hsconfig"
            or not all(_is_canonical_repository_component(part) for part in parts)
            or relative in result
            or folded_path in folded
        ):
            raise RuntimeLockError("local project committed tree is invalid")
        result[relative] = oid
        folded.add(folded_path)
    if not result:
        raise RuntimeLockError("local project committed tree is empty")
    return result


def _committed_local_payload(
    artifact: Mapping[str, object] | None,
    normalized_path: str,
    expected_oid: str,
) -> bytes:
    _local_repository_oids(artifact)
    repository = _local_repository_root(artifact)
    parts = normalized_path.split("/")
    if (
        len(parts) < 2
        or parts[0] != "hsconfig"
        or any(part in {"", ".", ".."} for part in parts)
        or re.fullmatch(r"[0-9a-f]{40}", expected_oid) is None
    ):
        raise RuntimeLockError("local project committed source path is invalid")
    return _bound_git_output(
        "cat-file",
        "blob",
        expected_oid,
        maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
        repository=repository,
    )


def _matches_committed_local_payload(
    installed: bytes,
    committed: bytes,
    normalized_path: str,
) -> bool:
    if installed == committed:
        return True
    if Path(normalized_path).suffix not in {".json", ".py"}:
        return False
    if b"\r" in committed or b"\x00" in committed:
        return False
    try:
        committed.decode("utf-8")
        installed.decode("utf-8")
    except UnicodeError:
        return False
    return installed == committed.replace(b"\n", b"\r\n")


def _matches_materialized_git_payload(
    materialized: bytes,
    committed: bytes,
    normalized_path: str,
) -> bool:
    if materialized == committed:
        return True
    if Path(normalized_path).suffix not in {".json", ".py"}:
        return False
    if b"\x00" in materialized or b"\r" in materialized.replace(b"\r\n", b""):
        return False
    try:
        materialized.decode("utf-8")
        committed.decode("utf-8")
    except UnicodeError:
        return False
    return materialized.replace(b"\r\n", b"\n") == committed


def _assert_materialized_repository_source(path: Path) -> bytes:
    try:
        relative = path.relative_to(ROOT)
        current = ROOT
        directories: list[tuple[Path, _PathIdentity]] = []
        for part in relative.parts[:-1]:
            metadata = current.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or _is_reparse(metadata)
            ):
                raise RuntimeLockError("local project repository path is unsafe")
            directories.append((current, _identity(metadata)))
            current /= part
        source, _metadata = _read_bound_regular_file(
            path,
            maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
            error_type=RuntimeLockError,
            label="local project repository source",
        )
        for directory, expected in directories:
            if _identity(directory.lstat()) != expected:
                raise RuntimeLockError("local project repository path changed")
        return source
    except ValueError as exc:
        raise RuntimeLockError("local project repository path is invalid") from exc


def _assert_local_repository_binding(
    artifact: Mapping[str, object] | None,
) -> None:
    commit_oid, tree_oid = _local_repository_oids(artifact)
    repository = _local_repository_root(artifact)
    try:
        head = _bound_git_oid("HEAD", repository=repository)
        head_tree = _bound_git_oid("HEAD^{tree}", repository=repository)
        committed_tree = _bound_git_oid(
            f"{commit_oid}^{{tree}}",
            repository=repository,
        )
        status = _bound_git_output(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            maximum_bytes=1024 * 1024,
            repository=repository,
        )
        _assert_default_git_index(repository=repository)
    except UnicodeError as exc:
        raise RuntimeLockError("local project repository binding is invalid") from exc
    if (
        head != commit_oid
        or head_tree != tree_oid
        or committed_tree != tree_oid
        or status != b""
    ):
        raise RuntimeLockError("local project repository binding differs")


def _assert_bound_local_artifact(
    artifact: Mapping[str, object] | None,
) -> str:
    if artifact is None:
        raise RuntimeLockError("local project artifact binding is missing")
    try:
        artifact_name = artifact["name"]
        artifact_version = artifact["version"]
        wheel_path = Path(str(artifact["wheel_path"]))
        digest = artifact["sha256"]
        wheel_source = artifact["_wheel_source"]
        disk_source, _metadata = _read_bound_regular_file(
            wheel_path,
            maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
            error_type=RuntimeLockError,
            label="local project wheel",
        )
        inventory = _wheel_inventory(wheel_source)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise RuntimeLockError("local project artifact binding is invalid") from exc
    if (
        not isinstance(artifact_name, str)
        or _normalized_name(artifact_name) != "hsconfig"
        or not isinstance(artifact_version, str)
        or not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or not isinstance(wheel_source, bytes)
        or disk_source != wheel_source
        or hashlib.sha256(wheel_source).hexdigest() != digest
        or artifact.get("files") != inventory
    ):
        raise RuntimeLockError("local project artifact binding differs")
    normalized_name = re.sub(r"[^A-Za-z0-9.]+", "_", artifact_name)
    normalized_version = re.sub(r"[^A-Za-z0-9.]+", "_", artifact_version)
    expected_dist_info = f"{normalized_name}-{normalized_version}.dist-info"
    inventory_paths = {
        str(row["path"])
        for row in inventory
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    top_level_dist_info = {
        path.split("/", 1)[0]
        for path in inventory_paths
        if path.split("/", 1)[0].endswith(".dist-info")
    }
    if (
        top_level_dist_info != {expected_dist_info}
        or f"{expected_dist_info}/RECORD" not in inventory_paths
    ):
        raise RuntimeLockError("local project artifact inventory is invalid")
    return expected_dist_info


def _assert_bound_local_direct_url(
    direct_url: str,
    artifact: Mapping[str, object] | None,
    dist_info_root: str,
) -> tuple[str, bytes]:
    if artifact is None:
        raise RuntimeLockError("local project origin is unverifiable")
    try:
        payload = json.loads(direct_url, object_pairs_hook=_closed_object)
        wheel_path = Path(str(artifact["wheel_path"])).resolve(strict=True)
        digest = str(artifact["sha256"])
        direct_url_source = direct_url.encode("utf-8")
    except (json.JSONDecodeError, OSError, TypeError, UnicodeError, ValueError, KeyError) as exc:
        raise RuntimeLockError("local project origin is unverifiable") from exc
    if payload != {
        "archive_info": {
            "hash": f"sha256={digest}",
            "hashes": {"sha256": digest},
        },
        "url": wheel_path.as_uri(),
    }:
        raise RuntimeLockError("local project origin differs from committed wheel")
    return f"{dist_info_root}/direct_url.json", direct_url_source


def _assert_bound_nonlocal_direct_url(
    direct_url: str,
    artifact: Mapping[str, object] | None,
) -> tuple[str, bytes]:
    if artifact is None:
        raise RuntimeLockError("installed package origin is unverifiable")
    try:
        payload = json.loads(direct_url, object_pairs_hook=_closed_object)
        artifact_name = artifact["name"]
        artifact_version = artifact["version"]
        wheel_path = Path(str(artifact["wheel_path"])).resolve(strict=True)
        digest = str(artifact["sha256"])
        wheel_source = artifact["_wheel_source"]
        bootstrap_root = Path(sys.prefix).resolve(strict=True).parent
        disk_source, _identity = _read_bound_regular_file(
            wheel_path,
            maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
            error_type=RuntimeLockError,
            label="runtime bootstrap wheel",
        )
        inventory = _wheel_inventory(wheel_source)
        inventory_paths = {
            row["path"]
            for row in inventory
            if isinstance(row, dict) and isinstance(row.get("path"), str)
        }
        dist_info_roots = {
            path.split("/", 1)[0]
            for path in inventory_paths
            if path.split("/", 1)[0].endswith(".dist-info")
        }
        normalized_name = re.sub(r"[^A-Za-z0-9.]+", "_", artifact_name)
        normalized_version = re.sub(r"[^A-Za-z0-9.]+", "_", artifact_version)
        expected_dist_info = f"{normalized_name}-{normalized_version}.dist-info"
        expected_direct_url_path = f"{expected_dist_info}/direct_url.json"
        direct_url_source = direct_url.encode("utf-8")
        bound_origin_url = wheel_path.as_uri()
        if (
            _normalized_name(artifact_name) == "pip"
            and payload.get("url") != bound_origin_url
        ):
            initial_wheel = (bootstrap_root / wheel_path.name).resolve(strict=True)
            initial_source, _initial_identity = _read_bound_regular_file(
                initial_wheel,
                maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
                error_type=RuntimeLockError,
                label="initial pip bootstrap wheel",
            )
            if (
                wheel_path.parent == bootstrap_root / "dependency-wheels"
                and initial_wheel.parent == bootstrap_root
                and initial_source == wheel_source
            ):
                bound_origin_url = initial_wheel.as_uri()
    except (
        json.JSONDecodeError,
        OSError,
        UnicodeError,
        TypeError,
        ValueError,
        KeyError,
        RuntimeLockError,
    ) as exc:
        raise RuntimeLockError("installed package origin is unverifiable") from exc
    if (
        not isinstance(wheel_source, bytes)
        or not isinstance(artifact_name, str)
        or not isinstance(artifact_version, str)
        or not normalized_name
        or not normalized_version
        or artifact.get("install") is not True
        or artifact.get("allowed_startup_surfaces") != []
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or bootstrap_root not in wheel_path.parents
        or ROOT in wheel_path.parents
        or disk_source != wheel_source
        or hashlib.sha256(wheel_source).hexdigest() != digest
        or artifact.get("files") != inventory
        or dist_info_roots != {expected_dist_info}
        or f"{expected_dist_info}/RECORD" not in inventory_paths
        or payload
        != {
                "archive_info": {
                    "hash": f"sha256={digest}",
                    "hashes": {"sha256": digest},
                },
                "url": bound_origin_url,
            }
    ):
        raise RuntimeLockError("installed package origin differs from bound artifact")
    return expected_direct_url_path, direct_url_source


def _assert_distribution_origin(
    distribution: Any,
    *,
    local_project: bool,
    artifact: Mapping[str, object] | None = None,
) -> set[Path]:
    installer = _distribution_text(distribution, "INSTALLER")
    wheel = _distribution_text(distribution, "WHEEL")
    record = _distribution_text(distribution, "RECORD")
    direct_url = _distribution_text(distribution, "direct_url.json")
    if not local_project and artifact is not None and artifact.get("install") is False:
        try:
            root = Path(distribution.locate_file("")).resolve(strict=True)
            runtime_root = Path(str(artifact.get("_runtime_root", ""))).resolve(strict=True)
        except (AttributeError, OSError) as exc:
            raise RuntimeLockError("runtime overlay origin is unverifiable") from exc
        install, allowed_startup_surfaces = _runtime_startup_surface_policy(
            artifact.get("name"), artifact.get("version")
        )
        if (
            install
            or artifact.get("allowed_startup_surfaces") != list(allowed_startup_surfaces)
            or root != runtime_root
            or installer is not None
            or wheel is None
            or record is None
            or direct_url is not None
        ):
            raise RuntimeLockError("runtime overlay origin differs from bound artifact")
        return set()
    if installer != "pip\n" or wheel is None or record is None:
        raise RuntimeLockError("installed package artifact identity is unverifiable")
    try:
        root = Path(distribution.locate_file("")).resolve(strict=True)
        allowed = {
            Path(value).resolve(strict=True)
            for key, value in sysconfig.get_paths().items()
            if key in {"purelib", "platlib"}
        }
    except (AttributeError, OSError) as exc:
        raise RuntimeLockError("installed package origin is unverifiable") from exc
    if root not in allowed:
        raise RuntimeLockError("installed package origin differs from project lock")
    bound_nonlocal_direct_url: tuple[str, bytes] | None = None
    bound_local_direct_url: tuple[str, bytes] | None = None
    committed_package_tree: dict[str, str] | None = None
    if local_project and artifact is not None:
        dist_info_root = _assert_bound_local_artifact(artifact)
        committed_package_tree = _committed_local_tree(artifact)
    if local_project and artifact is None:
        try:
            payload = json.loads(direct_url or "", object_pairs_hook=_closed_object)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise RuntimeLockError("local project origin is unverifiable") from exc
        if payload != {"dir_info": {}, "url": ROOT.as_uri()}:
            raise RuntimeLockError("local project origin differs from repository")
    elif not local_project and direct_url is not None:
        bound_nonlocal_direct_url = _assert_bound_nonlocal_direct_url(
            direct_url,
            artifact,
        )
    elif local_project:
        bound_local_direct_url = _assert_bound_local_direct_url(
            direct_url or "",
            artifact,
            dist_info_root,
        )
    try:
        rows = list(csv.reader(io.StringIO(record)))
    except csv.Error as exc:
        raise RuntimeLockError("installed package artifact identity is unverifiable") from exc
    if not rows or any(len(row) != 3 or not row[0] for row in rows):
        raise RuntimeLockError("installed package artifact identity is unverifiable")
    installation_root = Path(sys.prefix).resolve(strict=True)
    seen_paths: set[str] = set()
    verified_paths: set[Path] = set()
    installed_package_paths: set[str] = set()
    verified_hashes = 0
    bound_direct_url_payload_seen = False
    bound_local_direct_url_payload_seen = False
    for relative_name, encoded_hash, encoded_size in rows:
        normalized_path = relative_name.replace("\\", "/")
        if normalized_path in seen_paths:
            raise RuntimeLockError("installed package artifact identity is unverifiable")
        seen_paths.add(normalized_path)
        if not encoded_hash:
            if not (
                normalized_path.endswith(".dist-info/RECORD")
                or (
                    "/__pycache__/" in f"/{normalized_path}"
                    and normalized_path.endswith(".pyc")
                )
            ):
                raise RuntimeLockError("installed package contains unhashed payload")
            try:
                optional_path = (root / Path(*normalized_path.split("/"))).resolve(strict=True)
            except OSError:
                if normalized_path.endswith(".pyc"):
                    continue
                raise RuntimeLockError("installed package metadata payload is missing")
            if normalized_path.endswith(".pyc"):
                raise RuntimeLockError("runtime bytecode payload is not permitted")
            verified_paths.add(optional_path)
            continue
        try:
            algorithm, encoded_digest = encoded_hash.split("=", 1)
            expected_digest = base64.urlsafe_b64decode(
                encoded_digest + "=" * (-len(encoded_digest) % 4)
            )
            expected_size = int(encoded_size)
            original_path = root / Path(*normalized_path.split("/"))
            original_metadata = original_path.lstat()
            if (
                not stat.S_ISREG(original_metadata.st_mode)
                or stat.S_ISLNK(original_metadata.st_mode)
                or _is_reparse(original_metadata)
            ):
                raise RuntimeLockError(
                    "installed package artifact identity is unverifiable"
                )
            installed_path = original_path.resolve(strict=True)
            resolved_metadata = installed_path.lstat()
            if (resolved_metadata.st_dev, resolved_metadata.st_ino) != (
                original_metadata.st_dev,
                original_metadata.st_ino,
            ):
                raise RuntimeLockError("installed package path changed during resolution")
        except (OSError, ValueError) as exc:
            raise RuntimeLockError(
                "installed package artifact identity is unverifiable"
            ) from exc
        if (
            algorithm != "sha256"
            or len(expected_digest) != hashlib.sha256().digest_size
            or expected_size < 0
            or not (
                installed_path == installation_root
                or installation_root in installed_path.parents
            )
        ):
            raise RuntimeLockError("installed package artifact identity is unverifiable")
        try:
            payload, installed_metadata = _read_bound_regular_file(
                installed_path,
                maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
                error_type=RuntimeLockError,
                label="installed package payload",
            )
            if installed_metadata.st_size != expected_size:
                raise RuntimeLockError("installed package artifact identity is unverifiable")
        except OSError as exc:
            raise RuntimeLockError(
                "installed package artifact identity is unverifiable"
            ) from exc
        if hashlib.sha256(payload).digest() != expected_digest:
            raise RuntimeLockError("installed package artifact identity differs from metadata")
        if (
            bound_nonlocal_direct_url is not None
            and normalized_path == bound_nonlocal_direct_url[0]
        ):
            if payload != bound_nonlocal_direct_url[1]:
                raise RuntimeLockError(
                    "installed package origin differs from bound artifact"
                )
            bound_direct_url_payload_seen = True
        if (
            bound_local_direct_url is not None
            and normalized_path == bound_local_direct_url[0]
        ):
            if payload != bound_local_direct_url[1]:
                raise RuntimeLockError(
                    "local project origin differs from committed wheel"
                )
            bound_local_direct_url_payload_seen = True
        verified_paths.add(installed_path)
        if local_project and normalized_path.startswith("hsconfig/"):
            repository_path = ROOT / "src" / Path(*normalized_path.split("/"))
            try:
                if committed_package_tree is None:
                    raise RuntimeLockError("local project committed tree is missing")
                committed_oid = committed_package_tree.get(normalized_path)
                if committed_oid is None:
                    raise RuntimeLockError(
                        "local project installation differs from committed tree"
                    )
                materialized_payload = _assert_materialized_repository_source(
                    repository_path
                )
                committed_payload = _committed_local_payload(
                    artifact,
                    normalized_path,
                    committed_oid,
                )
                if not (
                    _matches_materialized_git_payload(
                        materialized_payload,
                        committed_payload,
                        normalized_path,
                    )
                    and _matches_committed_local_payload(
                        payload,
                        committed_payload,
                        normalized_path,
                    )
                ):
                    raise RuntimeLockError(
                        "local project installation differs from repository"
                    )
            except OSError as exc:
                raise RuntimeLockError(
                    "local project installation differs from repository"
                ) from exc
            installed_package_paths.add(normalized_path)
        verified_hashes += 1
    if verified_hashes == 0:
        raise RuntimeLockError("installed package artifact identity is unverifiable")
    if bound_nonlocal_direct_url is not None and not bound_direct_url_payload_seen:
        raise RuntimeLockError("installed package origin differs from bound artifact")
    if bound_local_direct_url is not None and not bound_local_direct_url_payload_seen:
        raise RuntimeLockError("local project origin differs from committed wheel")
    if artifact is not None:
        expected_paths = _wheel_installed_paths(artifact, root)
        record_paths = {
            path for path in seen_paths if "/__pycache__/" not in f"/{path}"
        }
        additions = {
            path
            for path in record_paths - expected_paths
            if path.endswith(".dist-info/INSTALLER")
            or path.endswith(".dist-info/REQUESTED")
            or (
                bound_local_direct_url is not None
                and path == bound_local_direct_url[0]
            )
            or (
                bound_nonlocal_direct_url is not None
                and path == bound_nonlocal_direct_url[0]
            )
        }
        scripts = _entry_point_script_paths(artifact, root)
        if record_paths != expected_paths | additions | (record_paths & scripts):
            raise RuntimeLockError("installed RECORD differs from selected wheel inventory")
    if local_project:
        if committed_package_tree is None:
            raise RuntimeLockError("local project committed tree is missing")
        if installed_package_paths != set(committed_package_tree):
            raise RuntimeLockError("local project installation differs from repository")
        _assert_local_repository_binding(artifact)
    return verified_paths


def _is_expected_linux_lib64_link(path: Path, environment_root: Path) -> bool:
    if os.name == "nt" or sys.platform != "linux" or sys.maxsize <= 2**32:
        return False
    try:
        if os.readlink(path) != "lib":
            return False
        expected = environment_root / "lib"
        expected_metadata = expected.lstat()
        target_metadata = path.stat()
        return (
            stat.S_ISDIR(expected_metadata.st_mode)
            and not stat.S_ISLNK(expected_metadata.st_mode)
            and not _is_reparse(expected_metadata)
            and path.resolve(strict=True) == expected.resolve(strict=True)
            and (target_metadata.st_dev, target_metadata.st_ino)
            == (expected_metadata.st_dev, expected_metadata.st_ino)
        )
    except OSError:
        return False


def _assert_runtime_tree_closed(
    claimed_paths: set[Path],
    environment_root: Path,
) -> None:
    observed: set[Path] = set()
    environment_root = environment_root.resolve(strict=True)
    infrastructure: set[Path] = set()
    for path in environment_root.rglob("*"):
        metadata = path.lstat()
        relative = path.relative_to(environment_root).as_posix()
        infrastructure_name = relative == "pyvenv.cfg" or re.fullmatch(
            r"(?:Scripts|bin)/(?:Activate\.ps1|activate(?:\.bat|\.fish|\.csh)?|"
            r"deactivate\.bat|python(?:3(?:\.\d+)?)?(?:\.exe)?|pythonw\.exe)",
            relative,
        ) is not None
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            if relative == "lib64" and _is_expected_linux_lib64_link(
                path, environment_root
            ):
                infrastructure.add(path)
                continue
            if not infrastructure_name:
                raise RuntimeLockError("runtime installation contains linked payload")
            try:
                link_target = path.resolve(strict=True)
            except OSError as exc:
                raise RuntimeLockError(
                    "runtime installation contains unsafe infrastructure link"
                ) from exc
            allowed_interpreters = {
                Path(sys.executable).resolve(strict=True),
                Path(getattr(sys, "_base_executable", sys.executable)).resolve(
                    strict=True
                ),
            }
            if link_target not in allowed_interpreters:
                raise RuntimeLockError(
                    "runtime installation infrastructure link target differs"
                )
            infrastructure.add(link_target)
        elif stat.S_ISREG(metadata.st_mode):
            resolved = path.resolve(strict=True)
            (infrastructure if infrastructure_name else observed).add(resolved)
        elif not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeLockError("runtime installation contains unsafe payload")
    if observed != claimed_paths:
        raise RuntimeLockError("runtime installation contains unrecorded payload")


def _assert_runtime_matches_lock(
    lock_file: Path = LOCK_FILE,
) -> _CoverageRuntimeBinding | None:
    with _runtime_lock_phase(RuntimeLockCategory.ARTIFACT_BINDING):
        locked = _locked_versions(lock_file)
    with _runtime_lock_phase(RuntimeLockCategory.MANIFEST_BINDING):
        artifacts = _load_runtime_manifest(lock_file, locked)
    with _runtime_lock_phase(RuntimeLockCategory.DISTRIBUTION_SET):
        visible: dict[str, list[Any]] = {}
        for distribution in importlib_metadata.distributions():
            name = distribution.metadata.get("Name")
            if not isinstance(name, str) or not name:
                raise RuntimeLockError("installed package identity is invalid")
            visible.setdefault(_normalized_name(name), []).append(distribution)
        expected_names = set(locked) | {"hsconfig"}
        if set(visible) != expected_names:
            raise RuntimeLockError("installed package set differs from project lock")
    claimed_paths: set[Path] = set()
    for normalized, (_name, expected_version) in locked.items():
        with _runtime_lock_phase(RuntimeLockCategory.DISTRIBUTION_SET):
            distributions = visible[normalized]
            if len(distributions) != 1:
                raise RuntimeLockError(
                    "locked package has duplicate visible distributions"
                )
            distribution = distributions[0]
        with _runtime_lock_phase(RuntimeLockCategory.DISTRIBUTION_VERSION):
            if str(distribution.version) != expected_version:
                raise RuntimeLockError(
                    "installed package version differs from project lock"
                )
        with _runtime_lock_phase(RuntimeLockCategory.DISTRIBUTION_ORIGIN):
            claimed_paths.update(
                _assert_distribution_origin(
                    distribution,
                    local_project=False,
                    artifact=artifacts[normalized] if artifacts is not None else None,
                )
            )
    with _runtime_lock_phase(RuntimeLockCategory.LOCAL_PROJECT_BINDING):
        local = visible["hsconfig"]
        if len(local) != 1:
            raise RuntimeLockError("local project has duplicate visible distributions")
        project_source, _ = _read_bound_regular_file(
            ROOT / "pyproject.toml",
            maximum_bytes=MAX_LOCK_BYTES,
            error_type=RuntimeLockError,
            label="project metadata",
        )
        try:
            project_document = tomllib.loads(project_source.decode("utf-8"))
            if project_document["project"].get("dynamic") != ["version"]:
                raise KeyError("dynamic version")
            version_source, _ = _read_bound_regular_file(
                ROOT / "src" / "hsconfig" / "version.py",
                maximum_bytes=MAX_LOCK_BYTES,
                error_type=RuntimeLockError,
                label="project version source",
            )
            version_tree = ast.parse(version_source.decode("utf-8"))
            version_values = [
                node.value.value
                for node in version_tree.body
                if isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "__version__"
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ]
            if len(version_values) != 1:
                raise KeyError("version source")
            project_version = version_values[0]
        except (
            UnicodeError,
            tomllib.TOMLDecodeError,
            SyntaxError,
            KeyError,
            TypeError,
        ) as exc:
            raise RuntimeLockError("project metadata version is invalid") from exc
        if (
            not isinstance(project_version, str)
            or str(local[0].version) != project_version
        ):
            raise RuntimeLockError("local project version differs from repository")
        claimed_paths.update(
            _assert_distribution_origin(
                local[0],
                local_project=True,
                artifact=artifacts["hsconfig"] if artifacts is not None else None,
            )
        )
    if artifacts is not None:
        with _runtime_lock_phase(RuntimeLockCategory.RUNTIME_TREE_CLOSURE):
            _assert_runtime_tree_closed(claimed_paths, Path(sys.prefix))
        with _runtime_lock_phase(RuntimeLockCategory.MANIFEST_BINDING):
            manifest_root = Path(
                os.environ["HSCONFIG_RUNTIME_MANIFEST"]
            ).parent.resolve(strict=True)
        local_artifact = artifacts["hsconfig"]
        repository_root = _local_repository_root(local_artifact)
        commit_oid, tree_oid = _local_repository_oids(local_artifact)
        root_identity = _local_repository_root_identity(local_artifact)
        try:
            current_root_identity = _identity(repository_root.lstat())
        except OSError as exc:
            raise RuntimeLockError(
                "local project repository binding is invalid"
            ) from exc
        if current_root_identity != root_identity:
            raise RuntimeLockError("local project repository binding differs")
        return _CoverageRuntimeBinding(
            repository_root=repository_root,
            commit_oid=commit_oid,
            tree_oid=tree_oid,
            root_identity=root_identity,
            pythonpath=(
                manifest_root / "committed-source",
                manifest_root / "build-backend",
            ),
            source_inventory=local_artifact["_source_inventory"],
            build_backend_identity=local_artifact["_build_backend_identity"],
            build_backend_inventory_sha256=local_artifact[
                "_build_backend_inventory_sha256"
            ],
        )
    return None


def _coverage_directory_identity(run_root: Path) -> tuple[int, int]:
    try:
        metadata = run_root.lstat()
    except OSError as exc:
        raise CoverageGateError("coverage run directory cannot be inspected") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
    ):
        raise CoverageGateError("coverage run directory is unsafe")
    return metadata.st_dev, metadata.st_ino


def _windows_host() -> bool:
    return os.name == "nt"


def _validated_temporary_root(
    candidate: Path,
    *,
    label: str,
    forbidden_roots: tuple[Path, ...] = (),
) -> Path:
    if not candidate.is_absolute():
        raise CoverageGateError(f"{label} must be absolute")
    try:
        metadata = candidate.lstat()
    except OSError as exc:
        raise CoverageGateError(f"{label} cannot be inspected") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
    ):
        raise CoverageGateError(f"{label} is unsafe")
    try:
        root = candidate.resolve(strict=True)
        resolved_metadata = root.lstat()
    except OSError as exc:
        raise CoverageGateError(f"{label} cannot be resolved") from exc
    forbidden = (ROOT, *forbidden_roots)
    if _identity(resolved_metadata) != _identity(metadata):
        raise CoverageGateError(f"{label} is unsafe")
    for forbidden_root in forbidden:
        try:
            canonical_forbidden = forbidden_root.resolve(strict=True)
        except OSError as exc:
            raise CoverageGateError(f"{label} boundary cannot be resolved") from exc
        if root == canonical_forbidden or canonical_forbidden in root.parents:
            raise CoverageGateError(f"{label} is unsafe")
    return root


def _windows_pytest_path_within_budget(parent: Path) -> bool:
    projected_root = parent / (
        PYTEST_TEMP_PREFIX + ("x" * PYTEST_TEMP_NAME_BUDGET)
    )
    projected = projected_root / Path(_WINDOWS_PYTEST_PROJECTED_SUFFIX)
    return len(str(projected)) <= MAX_WINDOWS_PYTEST_PATH


def _pytest_temporary_parent(
    temporary_root: Path,
    *,
    forbidden_roots: tuple[Path, ...],
) -> Path:
    if not _windows_host():
        return temporary_root
    runner_temp = os.environ.get("RUNNER_TEMP")
    if runner_temp:
        try:
            candidate = _validated_temporary_root(
                Path(runner_temp),
                label="pytest runner temporary root",
                forbidden_roots=forbidden_roots,
            )
            if _windows_pytest_path_within_budget(candidate):
                return candidate
        except (CoverageGateError, OSError, ValueError):
            pass
    if not _windows_pytest_path_within_budget(temporary_root):
        raise CoverageGateError("pytest temporary path exceeds Windows budget")
    return temporary_root


def _create_owned_directory(
    temporary_root: Path,
    *,
    prefix: str,
    label: str,
) -> tuple[Path, tuple[int, int]]:
    raw_path: Path | None = None
    identity: tuple[int, int] | None = None
    try:
        raw_path = Path(tempfile.mkdtemp(prefix=prefix, dir=temporary_root))
        if not raw_path.is_absolute() or raw_path.parent != temporary_root:
            raise CoverageGateError(f"{label} escaped temporary root")
        metadata = raw_path.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
        ):
            raise CoverageGateError(f"{label} is unsafe")
        identity = (metadata.st_dev, metadata.st_ino)
        if raw_path.resolve(strict=True) != raw_path:
            raise CoverageGateError(f"{label} escaped temporary root")
        if _coverage_directory_identity(raw_path) != identity:
            raise CoverageGateError(f"{label} changed during setup")
        return raw_path, identity
    except BaseException as exc:
        if raw_path is not None:
            try:
                cleanup_metadata = raw_path.lstat()
            except OSError:
                cleanup_metadata = None
            if (
                cleanup_metadata is not None
                and stat.S_ISDIR(cleanup_metadata.st_mode)
                and not stat.S_ISLNK(cleanup_metadata.st_mode)
                and not _is_reparse(cleanup_metadata)
                and raw_path.parent == temporary_root
            ):
                cleanup_identity = (
                    cleanup_metadata.st_dev,
                    cleanup_metadata.st_ino,
                )
                if identity is None:
                    exc.add_note(
                        "temporary setup cleanup skipped because ownership was not "
                        "established"
                    )
                elif cleanup_identity == identity:
                    try:
                        _cleanup_owned_run_root(
                            temporary_root,
                            raw_path,
                            cleanup_identity,
                        )
                    except BaseException as cleanup_error:
                        exc.add_note(
                            "additional temporary setup cleanup failure: "
                            f"{type(cleanup_error).__name__}: {cleanup_error}"
                        )
        raise


def _find_owned_directory(
    temporary_root: Path,
    requested_path: Path,
    expected_identity: tuple[int, int],
) -> Path | None:
    if requested_path.parent != temporary_root:
        return None
    candidates = [requested_path]
    try:
        candidates.extend(temporary_root.iterdir())
    except OSError:
        return None
    matches: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            metadata = candidate.lstat()
        except OSError:
            continue
        if (
            stat.S_ISDIR(metadata.st_mode)
            and not stat.S_ISLNK(metadata.st_mode)
            and not _is_reparse(metadata)
            and (metadata.st_dev, metadata.st_ino) == expected_identity
        ):
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _assert_coverage_cleanup_authority(
    temporary_root: Path,
    expected_temporary_root_identity: tuple[int, int] | None,
) -> None:
    if expected_temporary_root_identity is None:
        return
    try:
        temporary_root_metadata = temporary_root.lstat()
    except OSError as exc:
        raise CoverageGateError(
            "coverage cleanup authority cannot be inspected"
        ) from exc
    if (
        (temporary_root_metadata.st_dev, temporary_root_metadata.st_ino)
        != expected_temporary_root_identity
        or temporary_root.resolve(strict=True) != temporary_root
        or not stat.S_ISDIR(temporary_root_metadata.st_mode)
        or stat.S_ISLNK(temporary_root_metadata.st_mode)
        or _is_reparse(temporary_root_metadata)
    ):
        raise CoverageGateError("coverage cleanup authority changed")


def _windows_quarantine_owned_run_root(
    temporary_root: Path,
    owned: Path,
    expected_identity: tuple[int, int],
    quarantine: Path,
    expected_temporary_root_identity: tuple[int, int] | None,
) -> None:
    import ctypes
    from ctypes import wintypes

    class _FileId128(ctypes.Structure):
        _fields_ = (("identifier", ctypes.c_ubyte * 16),)

    class _FileIdInfo(ctypes.Structure):
        _fields_ = (
            ("volume_serial_number", ctypes.c_ulonglong),
            ("file_id", _FileId128),
        )

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("file_attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("last_access_time", wintypes.FILETIME),
            ("last_write_time", wintypes.FILETIME),
            ("volume_serial_number", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("number_of_links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        )

    class _FileRenameInfo(ctypes.Structure):
        _fields_ = (
            ("flags", wintypes.DWORD),
            ("root_directory", wintypes.HANDLE),
            ("file_name_length", wintypes.DWORD),
            ("file_name", wintypes.WCHAR * 1),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileInformationByHandleEx.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    )
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    invalid_handle = {0, -1, ctypes.c_void_p(-1).value}
    open_flags = 0x02000000 | 0x00200000
    share_read_write = 0x00000001 | 0x00000002

    def open_directory(path: Path, desired_access: int) -> int:
        handle = kernel32.CreateFileW(
            str(path),
            desired_access,
            share_read_write,
            None,
            3,
            open_flags,
            None,
        )
        if handle in invalid_handle:
            raise CoverageGateError("coverage run directory ownership was lost")
        return handle

    def handle_identity(handle: int) -> tuple[tuple[int, int], int]:
        legacy = _ByHandleFileInformation()
        if not kernel32.GetFileInformationByHandle(handle, ctypes.byref(legacy)):
            raise CoverageGateError("coverage run directory ownership was lost")
        legacy_identity = (
            legacy.volume_serial_number,
            (legacy.file_index_high << 32) | legacy.file_index_low,
        )
        if sys.version_info < (3, 12):
            return legacy_identity, legacy.file_attributes
        full = _FileIdInfo()
        if not kernel32.GetFileInformationByHandleEx(
            handle,
            18,
            ctypes.byref(full),
            ctypes.sizeof(full),
        ):
            raise CoverageGateError("coverage run directory ownership was lost")
        return (
            full.volume_serial_number,
            int.from_bytes(bytes(full.file_id.identifier), "little"),
        ), legacy.file_attributes

    authority_identity = (
        expected_temporary_root_identity
        if expected_temporary_root_identity is not None
        else _coverage_directory_identity(temporary_root)
    )
    authority_handle = open_directory(temporary_root, 0x00000020 | 0x00000080)
    owned_handle: int | None = None
    try:
        current_authority_identity, authority_attributes = handle_identity(
            authority_handle
        )
        if (
            current_authority_identity != authority_identity
            or not authority_attributes & 0x00000010
            or authority_attributes & 0x00000400
        ):
            raise CoverageGateError("coverage cleanup authority changed")
        owned_handle = open_directory(owned, 0x00010000 | 0x00000080)
        current_owned_identity, owned_attributes = handle_identity(owned_handle)
        if (
            current_owned_identity != expected_identity
            or not owned_attributes & 0x00000010
            or owned_attributes & 0x00000400
        ):
            raise CoverageGateError("coverage run directory ownership was lost")
        encoded_name = str(quarantine).encode("utf-16-le")
        file_name_offset = _FileRenameInfo.file_name.offset
        buffer_size = ctypes.sizeof(_FileRenameInfo) + len(encoded_name)
        rename_buffer = ctypes.create_string_buffer(buffer_size)
        rename_information = ctypes.cast(
            rename_buffer,
            ctypes.POINTER(_FileRenameInfo),
        ).contents
        rename_information.flags = 0
        rename_information.root_directory = None
        rename_information.file_name_length = len(encoded_name)
        ctypes.memmove(
            ctypes.addressof(rename_buffer) + file_name_offset,
            encoded_name,
            len(encoded_name),
        )
        if not kernel32.SetFileInformationByHandle(
            owned_handle,
            3,
            rename_buffer,
            buffer_size,
        ):
            rename_error = ctypes.get_last_error()
            raise ctypes.WinError(rename_error)
    finally:
        owned_closed = (
            True if owned_handle is None else bool(kernel32.CloseHandle(owned_handle))
        )
        authority_closed = bool(kernel32.CloseHandle(authority_handle))
        if not owned_closed or not authority_closed:
            raise CoverageGateError("coverage run quarantine handle cannot be closed")


def _quarantine_owned_run_root(
    temporary_root: Path,
    requested_path: Path,
    expected_identity: tuple[int, int],
    quarantine: Path,
    *,
    expected_temporary_root_identity: tuple[int, int] | None,
) -> None:
    windows_host = _windows_host()
    deadline = (
        time.monotonic() + WINDOWS_QUARANTINE_RENAME_TIMEOUT_SECONDS
        if windows_host
        else None
    )
    retry_error: OSError | None = None
    while True:
        if retry_error is not None:
            if deadline is None or time.monotonic() >= deadline:
                raise retry_error
        _assert_coverage_cleanup_authority(
            temporary_root,
            expected_temporary_root_identity,
        )
        owned = _find_owned_directory(
            temporary_root,
            requested_path,
            expected_identity,
        )
        if owned is None:
            raise CoverageGateError("coverage run directory ownership was lost")
        try:
            if windows_host:
                _windows_quarantine_owned_run_root(
                    temporary_root,
                    owned,
                    expected_identity,
                    quarantine,
                    expected_temporary_root_identity,
                )
            else:
                os.replace(owned, quarantine)
            return
        except OSError as exc:
            if (
                not windows_host
                or getattr(exc, "winerror", None) not in {5, 32}
                or deadline is None
            ):
                raise
            retry_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(WINDOWS_QUARANTINE_RENAME_POLL_SECONDS, remaining))


def _cleanup_owned_run_root(
    temporary_root: Path,
    requested_path: Path,
    expected_identity: tuple[int, int],
    *,
    expected_temporary_root_identity: tuple[int, int] | None = None,
) -> None:
    quarantine = temporary_root / f".hsconfig-coverage-quarantine-{os.getpid()}-{os.urandom(8).hex()}"
    try:
        _quarantine_owned_run_root(
            temporary_root,
            requested_path,
            expected_identity,
            quarantine,
            expected_temporary_root_identity=expected_temporary_root_identity,
        )
        if expected_temporary_root_identity is not None:
            current_temporary_root = temporary_root.lstat()
            if (
                (current_temporary_root.st_dev, current_temporary_root.st_ino)
                != expected_temporary_root_identity
                or temporary_root.resolve(strict=True) != temporary_root
                or not stat.S_ISDIR(current_temporary_root.st_mode)
                or stat.S_ISLNK(current_temporary_root.st_mode)
                or _is_reparse(current_temporary_root)
            ):
                raise CoverageGateError("coverage cleanup authority changed")
        if _coverage_directory_identity(quarantine) != expected_identity:
            raise CoverageGateError("coverage run quarantine identity changed")
        interrupted: BaseException | None = None
        for _attempt in range(3):
            try:
                _delete_owned_tree(quarantine, expected_identity)
                break
            except (KeyboardInterrupt, SystemExit) as exc:
                interrupted = exc
                continue
        if quarantine.exists() or quarantine.is_symlink():
            if interrupted is not None:
                raise interrupted
            raise CoverageGateError("coverage run cleanup left residue")
        if interrupted is not None:
            raise interrupted
    except CoverageGateError:
        raise
    except OSError as exc:
        raise CoverageGateError("coverage run cleanup failed") from exc
    if quarantine.exists() or quarantine.is_symlink():
        raise CoverageGateError("coverage run cleanup left residue")
    try:
        requested_metadata = requested_path.lstat()
    except OSError:
        return
    if (requested_metadata.st_dev, requested_metadata.st_ino) != expected_identity:
        raise CoverageGateError("coverage run directory was replaced")


def _delete_owned_tree(path: Path, expected_identity: tuple[int, int]) -> None:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CoverageGateError("coverage quarantine cannot be inspected") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or (metadata.st_dev, metadata.st_ino) != expected_identity
    ):
        raise CoverageGateError("coverage quarantine identity changed")
    if os.name == "nt":
        _delete_windows_entry(path, expected_identity)
    else:
        _delete_posix_tree(path, expected_identity)


def _delete_posix_tree(path: Path, expected_identity: tuple[int, int]) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != expected_identity:
            raise CoverageGateError("coverage quarantine identity changed")

        def empty(directory_descriptor: int) -> None:
            for name in os.listdir(directory_descriptor):
                child = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
                if stat.S_ISDIR(child.st_mode) and not stat.S_ISLNK(child.st_mode):
                    child_descriptor = os.open(name, flags, dir_fd=directory_descriptor)
                    try:
                        child_opened = os.fstat(child_descriptor)
                        if (child_opened.st_dev, child_opened.st_ino) != (
                            child.st_dev,
                            child.st_ino,
                        ):
                            raise CoverageGateError(
                                "coverage quarantine child identity changed"
                            )
                        empty(child_descriptor)
                    finally:
                        os.close(child_descriptor)
                    os.rmdir(name, dir_fd=directory_descriptor)
                else:
                    os.unlink(name, dir_fd=directory_descriptor)

        empty(descriptor)
        current = path.lstat()
        if (current.st_dev, current.st_ino) != expected_identity:
            raise CoverageGateError("coverage quarantine identity changed")
        os.rmdir(path)
    except OSError as exc:
        raise CoverageGateError("coverage quarantine cleanup failed") from exc
    finally:
        os.close(descriptor)


def _await_windows_delete_completion(
    path: Path,
    expected_metadata: os.stat_result,
) -> None:
    expected_identity = (expected_metadata.st_dev, expected_metadata.st_ino)
    expected_file_type = stat.S_IFMT(expected_metadata.st_mode)
    expected_symlink = stat.S_ISLNK(expected_metadata.st_mode)
    expected_reparse = _is_reparse(expected_metadata)
    deadline = time.monotonic() + WINDOWS_DELETE_SETTLE_TIMEOUT_SECONDS
    while True:
        try:
            current = path.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise CoverageGateError("coverage quarantine cleanup failed") from exc
        if (
            (current.st_dev, current.st_ino) != expected_identity
            or stat.S_IFMT(current.st_mode) != expected_file_type
            or stat.S_ISLNK(current.st_mode) is not expected_symlink
            or _is_reparse(current) is not expected_reparse
        ):
            raise CoverageGateError("coverage quarantine identity changed")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CoverageGateError("coverage quarantine cleanup left residue")
        time.sleep(min(WINDOWS_DELETE_SETTLE_POLL_SECONDS, remaining))


def _delete_windows_entry(
    path: Path,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    import ctypes
    from ctypes import wintypes

    class _FileId128(ctypes.Structure):
        _fields_ = (
            ("identifier", ctypes.c_ubyte * 16),
        )

    class _FileIdInfo(ctypes.Structure):
        _fields_ = (
            ("volume_serial_number", ctypes.c_ulonglong),
            ("file_id", _FileId128),
        )

    class _ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("file_attributes", wintypes.DWORD),
            ("creation_time", wintypes.FILETIME),
            ("last_access_time", wintypes.FILETIME),
            ("last_write_time", wintypes.FILETIME),
            ("volume_serial_number", wintypes.DWORD),
            ("file_size_high", wintypes.DWORD),
            ("file_size_low", wintypes.DWORD),
            ("number_of_links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        )

    class _FileDispositionInformationEx(ctypes.Structure):
        _fields_ = (
            ("flags", wintypes.DWORD),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.SetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandleEx.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.GetFileInformationByHandleEx.restype = wintypes.BOOL
    kernel32.GetFileInformationByHandle.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ByHandleFileInformation),
    )
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(
        str(path),
        0x00010000 | 0x00000100 | 0x00000080 | 0x00000001,
        0x00000001 | 0x00000002,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    if handle in {0, -1, ctypes.c_void_p(-1).value}:
        raise CoverageGateError("coverage quarantine handle cannot be opened")
    delete_marked = False
    handle_closed = False
    try:
        def handle_information() -> _FileIdInfo:
            information = _FileIdInfo()
            if not kernel32.GetFileInformationByHandleEx(
                handle,
                18,
                ctypes.byref(information),
                ctypes.sizeof(information),
            ):
                raise CoverageGateError("coverage quarantine handle identity cannot be read")
            return information

        def full_information_identity(
            information: _FileIdInfo,
        ) -> tuple[int, int]:
            return (
                information.volume_serial_number,
                int.from_bytes(bytes(information.file_id.identifier), "little"),
            )

        def legacy_path_identity() -> tuple[int, int]:
            information = _ByHandleFileInformation()
            if not kernel32.GetFileInformationByHandle(
                handle,
                ctypes.byref(information),
            ):
                raise CoverageGateError(
                    "coverage quarantine legacy handle identity cannot be read"
                )
            return (
                information.volume_serial_number,
                (information.file_index_high << 32) | information.file_index_low,
            )

        def path_compatible_handle_identity(
            full_identity: tuple[int, int],
        ) -> tuple[int, int]:
            if sys.version_info < (3, 12):
                return legacy_path_identity()
            return full_identity

        baseline_handle_identity = full_information_identity(handle_information())
        baseline_path_handle_identity = path_compatible_handle_identity(
            baseline_handle_identity
        )
        before = path.lstat()
        before_identity = (before.st_dev, before.st_ino)
        if (
            baseline_path_handle_identity != before_identity
            or (expected_identity is not None and before_identity != expected_identity)
        ):
            raise CoverageGateError("coverage quarantine identity changed")

        def assert_bound_identity() -> os.stat_result:
            current_handle_identity = full_information_identity(handle_information())
            current_path_handle_identity = path_compatible_handle_identity(
                current_handle_identity
            )
            current_path = path.lstat()
            current_path_identity = (current_path.st_dev, current_path.st_ino)
            if (
                current_handle_identity != baseline_handle_identity
                or current_path_handle_identity != current_path_identity
                or current_path_identity != before_identity
            ):
                raise CoverageGateError("coverage quarantine identity changed")
            return current_path

        if stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode) and not _is_reparse(before):
            for entry in list(os.scandir(path)):
                child_path = Path(entry.path)
                child_metadata = child_path.lstat()
                _delete_windows_entry(
                    child_path,
                    (child_metadata.st_dev, child_metadata.st_ino),
                )
        current_metadata = assert_bound_identity()
        disposition_flags = 0x00000001 | 0x00000002
        if getattr(current_metadata, "st_file_attributes", 0) & 0x00000001:
            disposition_flags |= 0x00000010
        disposition_ex = _FileDispositionInformationEx(flags=disposition_flags)
        if not kernel32.SetFileInformationByHandle(
            handle,
            21,
            ctypes.byref(disposition_ex),
            ctypes.sizeof(disposition_ex),
        ):
            raise CoverageGateError("coverage quarantine delete disposition failed")
        delete_marked = True
    except OSError as exc:
        raise CoverageGateError("coverage quarantine cleanup failed") from exc
    finally:
        handle_closed = bool(kernel32.CloseHandle(handle))
    if not handle_closed:
        raise CoverageGateError("coverage quarantine handle cannot be closed")
    if delete_marked:
        _await_windows_delete_completion(path, before)


def _identity_document(identity: _PathIdentity) -> dict[str, int]:
    return {
        "device": identity.device,
        "inode": identity.inode,
        "size": identity.size,
        "modified_ns": identity.modified_ns,
        "changed_ns": identity.changed_ns,
        "mode": identity.mode,
    }


def _runtime_inventory_digest(rows: object) -> str:
    return hashlib.sha256(
        json.dumps(
            rows,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _runtime_overlay_binding(root: Path) -> tuple[_PathIdentity, str]:
    try:
        before = root.lstat()
        if (
            not stat.S_ISDIR(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or _is_reparse(before)
        ):
            raise RuntimeLockError("runtime bootstrap overlay root is unsafe")
        resolved = root.resolve(strict=True)
        rows: list[dict[str, object]] = []
        for path in _runtime_regular_tree(
            resolved,
            label="runtime bootstrap overlay",
        ):
            payload, _ = _read_bound_regular_file(
                path,
                maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
                error_type=RuntimeLockError,
                label="runtime bootstrap overlay payload",
            )
            rows.append(
                {
                    "path": path.relative_to(resolved).as_posix(),
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        after = root.lstat()
    except OSError as exc:
        raise RuntimeLockError("runtime bootstrap overlay binding is unavailable") from exc
    if _identity(after) != _identity(before):
        raise RuntimeLockError("runtime bootstrap overlay root changed")
    return _identity(before), _runtime_inventory_digest(rows)


def _validated_runtime_executable(name: str) -> tuple[Path, _PathIdentity, str]:
    candidate_name = shutil.which(name, path=os.environ.get("PATH", ""))
    if candidate_name is None:
        raise CoverageGateError(f"locked {name} executable is unavailable")
    return _validated_runtime_file(Path(candidate_name), f"{name} executable")


def _validated_runtime_file(
    candidate: Path,
    label: str,
) -> tuple[Path, _PathIdentity, str]:
    try:
        if not candidate.is_absolute():
            raise CoverageGateError(f"locked {label} is unavailable")
        alias_before = candidate.lstat()
        alias_is_symlink = stat.S_ISLNK(alias_before.st_mode)
        if alias_is_symlink:
            if os.name != "posix" or _is_reparse(alias_before):
                raise CoverageGateError(f"locked {label} is unsafe")
            link_before = os.readlink(candidate)
        else:
            link_before = None
            if not stat.S_ISREG(alias_before.st_mode) or _is_reparse(alias_before):
                raise CoverageGateError(f"locked {label} is unsafe")
        resolved = candidate.resolve(strict=True)
        target_before = resolved.lstat()
        payload, opened = _read_bound_regular_file(
            resolved,
            maximum_bytes=128 * 1024 * 1024,
            error_type=CoverageGateError,
            label=f"locked {label}",
        )
        alias_after = candidate.lstat()
        resolved_after = candidate.resolve(strict=True)
        target_after = resolved.lstat()
        link_after = os.readlink(candidate) if alias_is_symlink else None
    except OSError as exc:
        raise CoverageGateError(f"locked {label} is unavailable") from exc
    if (
        not stat.S_ISREG(target_before.st_mode)
        or stat.S_ISLNK(target_before.st_mode)
        or _is_reparse(target_before)
        or _identity(alias_after) != _identity(alias_before)
        or link_after != link_before
        or resolved_after != resolved
        or _identity(target_after) != _identity(target_before)
        or not _same_regular_file_identity(opened, target_before)
    ):
        raise CoverageGateError(f"locked {label} is unsafe")
    return resolved, _identity(target_before), hashlib.sha256(payload).hexdigest()


def _same_regular_file_identity(
    opened: os.stat_result,
    path_metadata: os.stat_result,
) -> bool:
    opened_birthtime_ns = getattr(opened, "st_birthtime_ns", None)
    path_birthtime_ns = getattr(path_metadata, "st_birthtime_ns", None)
    timestamp_identity_matches = (
        opened_birthtime_ns == path_birthtime_ns
        if os.name == "nt"
        and opened_birthtime_ns is not None
        and path_birthtime_ns is not None
        else opened.st_ctime_ns == path_metadata.st_ctime_ns
    )
    return (
        opened.st_dev == path_metadata.st_dev
        and opened.st_ino == path_metadata.st_ino
        and opened.st_size == path_metadata.st_size
        and opened.st_mtime_ns == path_metadata.st_mtime_ns
        and timestamp_identity_matches
        and stat.S_ISREG(opened.st_mode)
        and stat.S_ISREG(path_metadata.st_mode)
    )


def _source_inventory_sha256(inventory: _RuntimeSourceInventory) -> str:
    rows = [
        {"path": path, "sha256": digest, "git_mode": mode}
        for path, digest, mode in inventory
    ]
    return _source_inventory_digest(rows)


def _locked_test_runtime_document(
    binding: _CoverageRuntimeBinding,
) -> tuple[str, _LockedTestRuntimeBinding]:
    source_root, build_backend_root = (
        path.resolve(strict=True) for path in binding.pythonpath
    )
    build_identity, build_digest = _runtime_overlay_binding(build_backend_root)
    if (
        build_identity != binding.build_backend_identity
        or build_digest != binding.build_backend_inventory_sha256
    ):
        raise CoverageGateError("locked runtime overlay differs")
    interpreter, interpreter_identity, interpreter_sha256 = _validated_runtime_file(
        Path(sys.executable), "python interpreter"
    )
    git_executable, git_identity, git_sha256 = _validated_runtime_executable("git")
    pwsh_executable, pwsh_identity, pwsh_sha256 = _validated_runtime_executable(
        "pwsh"
    )
    locked = _LockedTestRuntimeBinding(
        source_root=source_root,
        source_inventory_sha256=_source_inventory_sha256(binding.source_inventory),
        repository_root=binding.repository_root,
        commit_oid=binding.commit_oid,
        tree_oid=binding.tree_oid,
        root_identity=binding.root_identity,
        build_backend_root=build_backend_root,
        build_backend_identity=binding.build_backend_identity,
        build_backend_inventory_sha256=binding.build_backend_inventory_sha256,
        environment_root=Path(sys.prefix).resolve(strict=True),
        interpreter=interpreter,
        interpreter_identity=interpreter_identity,
        interpreter_sha256=interpreter_sha256,
        git_executable=git_executable,
        git_identity=git_identity,
        git_sha256=git_sha256,
        pwsh_executable=pwsh_executable,
        pwsh_identity=pwsh_identity,
        pwsh_sha256=pwsh_sha256,
    )
    document = {
        "schema_version": 1,
        "source_root": str(locked.source_root),
        "source_inventory_sha256": locked.source_inventory_sha256,
        "repository": str(locked.repository_root),
        "commit_oid": locked.commit_oid,
        "tree_oid": locked.tree_oid,
        "root_identity": _identity_document(locked.root_identity),
        "build_backend_root": str(locked.build_backend_root),
        "build_backend_identity": _identity_document(locked.build_backend_identity),
        "build_backend_inventory_sha256": locked.build_backend_inventory_sha256,
        "environment_root": str(locked.environment_root),
        "interpreter": str(locked.interpreter),
        "interpreter_identity": _identity_document(locked.interpreter_identity),
        "interpreter_sha256": locked.interpreter_sha256,
        "git_executable": str(locked.git_executable),
        "git_identity": _identity_document(locked.git_identity),
        "git_sha256": locked.git_sha256,
        "pwsh_executable": str(locked.pwsh_executable),
        "pwsh_identity": _identity_document(locked.pwsh_identity),
        "pwsh_sha256": locked.pwsh_sha256,
    }
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        locked,
    )


def _locked_test_runtime_binding(
    source: str,
    expected_sha256: str,
) -> _LockedTestRuntimeBinding:
    if type(source) is not str:
        raise CoverageGateError("locked test runtime binding is invalid")
    try:
        encoded = source.encode("utf-8")
        if (
            not encoded
            or len(encoded) > 32 * 1024
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
            or hashlib.sha256(encoded).hexdigest() != expected_sha256
        ):
            raise ValueError("binding size")
        document = json.loads(
            encoded,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError, UnicodeError, ValueError) as exc:
        raise CoverageGateError("locked test runtime binding is invalid") from exc
    expected = {
        "schema_version",
        "source_root",
        "source_inventory_sha256",
        "repository",
        "commit_oid",
        "tree_oid",
        "root_identity",
        "build_backend_root",
        "build_backend_identity",
        "build_backend_inventory_sha256",
        "environment_root",
        "interpreter",
        "interpreter_identity",
        "interpreter_sha256",
        "git_executable",
        "git_identity",
        "git_sha256",
        "pwsh_executable",
        "pwsh_identity",
        "pwsh_sha256",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise CoverageGateError("locked test runtime binding is invalid")
    schema_version = document["schema_version"]
    commit_oid = document["commit_oid"]
    tree_oid = document["tree_oid"]
    digests = (
        document["source_inventory_sha256"],
        document["build_backend_inventory_sha256"],
        document["interpreter_sha256"],
        document["git_sha256"],
        document["pwsh_sha256"],
    )
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
        or not isinstance(commit_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", commit_oid) is None
        or not isinstance(tree_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", tree_oid) is None
        or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in digests
        )
    ):
        raise CoverageGateError("locked test runtime binding is invalid")
    source_root = _coverage_scan_directory(document["source_root"])
    repository = _coverage_scan_directory(document["repository"])
    build_backend = _coverage_scan_directory(document["build_backend_root"])
    environment_root = _coverage_scan_directory(document["environment_root"])
    interpreter = _locked_runtime_file(document["interpreter"], "interpreter")
    git_executable = _locked_runtime_file(document["git_executable"], "git executable")
    pwsh_executable = _locked_runtime_file(
        document["pwsh_executable"], "pwsh executable"
    )
    locked = _LockedTestRuntimeBinding(
        source_root=source_root,
        source_inventory_sha256=str(document["source_inventory_sha256"]),
        repository_root=repository,
        commit_oid=commit_oid,
        tree_oid=tree_oid,
        root_identity=_coverage_scan_identity(document["root_identity"]),
        build_backend_root=build_backend,
        build_backend_identity=_coverage_scan_identity(document["build_backend_identity"]),
        build_backend_inventory_sha256=str(document["build_backend_inventory_sha256"]),
        environment_root=environment_root,
        interpreter=interpreter,
        interpreter_identity=_coverage_scan_identity(document["interpreter_identity"]),
        interpreter_sha256=str(document["interpreter_sha256"]),
        git_executable=git_executable,
        git_identity=_coverage_scan_identity(document["git_identity"]),
        git_sha256=str(document["git_sha256"]),
        pwsh_executable=pwsh_executable,
        pwsh_identity=_coverage_scan_identity(document["pwsh_identity"]),
        pwsh_sha256=str(document["pwsh_sha256"]),
    )
    if (
        locked.source_root != ROOT.resolve(strict=True)
        or locked.environment_root != Path(sys.prefix).resolve(strict=True)
        or locked.interpreter != Path(sys.executable).resolve(strict=True)
    ):
        raise CoverageGateError("locked test runtime binding differs")
    _assert_locked_tool_binding(locked)
    return locked


def _locked_runtime_file(value: object, label: str) -> Path:
    if type(value) is not str:
        raise CoverageGateError(f"locked {label} binding is invalid")
    try:
        candidate = Path(value)
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise CoverageGateError(f"locked {label} binding is invalid") from exc
    if (
        not candidate.is_absolute()
        or str(resolved) != value
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
    ):
        raise CoverageGateError(f"locked {label} binding is invalid")
    return resolved


def _assert_locked_tool_binding(binding: _LockedTestRuntimeBinding) -> None:
    try:
        build_identity, build_digest = _runtime_overlay_binding(
            binding.build_backend_root
        )
        (
            interpreter,
            interpreter_identity,
            interpreter_sha256,
        ) = _validated_runtime_file(
            binding.interpreter,
            "python interpreter",
        )
        git_source, git_metadata = _read_bound_regular_file(
            binding.git_executable,
            maximum_bytes=128 * 1024 * 1024,
            error_type=CoverageGateError,
            label="locked git executable",
        )
        git_path_metadata = binding.git_executable.lstat()
        pwsh_source, pwsh_metadata = _read_bound_regular_file(
            binding.pwsh_executable,
            maximum_bytes=128 * 1024 * 1024,
            error_type=CoverageGateError,
            label="locked pwsh executable",
        )
        pwsh_path_metadata = binding.pwsh_executable.lstat()
    except (OSError, RuntimeLockError) as exc:
        raise CoverageGateError("locked test tool binding is unavailable") from exc
    if (
        build_identity != binding.build_backend_identity
        or build_digest != binding.build_backend_inventory_sha256
        or interpreter != binding.interpreter
        or interpreter_identity != binding.interpreter_identity
        or interpreter_sha256 != binding.interpreter_sha256
        or _identity(git_path_metadata) != binding.git_identity
        or not _same_regular_file_identity(git_metadata, git_path_metadata)
        or hashlib.sha256(git_source).hexdigest() != binding.git_sha256
        or _identity(pwsh_path_metadata) != binding.pwsh_identity
        or not _same_regular_file_identity(pwsh_metadata, pwsh_path_metadata)
        or hashlib.sha256(pwsh_source).hexdigest() != binding.pwsh_sha256
    ):
        raise CoverageGateError("locked test tool binding differs")


def _assert_locked_test_runtime(
    binding: _LockedTestRuntimeBinding,
) -> _RuntimeSourceInventory:
    _assert_locked_tool_binding(binding)
    request = _CoverageScanRequest(
        source_root=binding.source_root,
        repository=binding.repository_root,
        outputs_root=binding.source_root,
        commit_oid=binding.commit_oid,
        tree_oid=binding.tree_oid,
        root_identity=binding.root_identity,
        tree_mode="working-pre-cutover",
        build_distributions=False,
    )
    _validate_coverage_scan_repository(request)
    repository_inventory = _coverage_scan_inventory(request)
    observed: list[dict[str, str]] = []
    observed_rows: list[_RuntimeSourceInventoryEntry] = []
    observed_paths: set[str] = set()
    for path in _runtime_regular_tree(
        binding.source_root,
        label="locked pytest source",
    ):
        relative = path.relative_to(binding.source_root).as_posix()
        expected = repository_inventory.get(relative)
        if expected is None:
            raise CoverageGateError("locked pytest source inventory differs")
        payload, metadata = _read_bound_regular_file(
            path,
            maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
            error_type=CoverageGateError,
            label="locked pytest source",
        )
        git_mode, _blob_oid = expected
        actual_mode = _runtime_git_mode(metadata.st_mode)
        if actual_mode is not None and actual_mode != git_mode:
            raise CoverageGateError("locked pytest source mode differs")
        observed_paths.add(relative)
        observed.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "git_mode": git_mode,
            }
        )
        observed_rows.append((relative, observed[-1]["sha256"], git_mode))
    if (
        observed_paths != set(repository_inventory)
        or _source_inventory_digest(observed) != binding.source_inventory_sha256
    ):
        raise CoverageGateError("locked pytest source inventory differs")
    return tuple(observed_rows)


def _closed_locked_test_path(binding: _LockedTestRuntimeBinding) -> str:
    directories = [
        binding.interpreter.parent.resolve(strict=True),
        binding.git_executable.parent.resolve(strict=True),
        binding.pwsh_executable.parent.resolve(strict=True),
    ]
    closed: list[str] = []
    for directory in directories:
        value = str(directory)
        if not any(directory == Path(existing) for existing in closed):
            closed.append(value)
    candidate = shutil.which("python", path=os.pathsep.join(closed))
    git_candidate = shutil.which("git", path=os.pathsep.join(closed))
    pwsh_candidate = shutil.which("pwsh", path=os.pathsep.join(closed))
    if (
        candidate is None
        or Path(candidate).resolve(strict=True) != binding.interpreter
        or git_candidate is None
        or Path(git_candidate).resolve(strict=True) != binding.git_executable
        or pwsh_candidate is None
        or Path(pwsh_candidate).resolve(strict=True) != binding.pwsh_executable
    ):
        raise CoverageGateError("locked test PATH binding differs")
    return os.pathsep.join(closed)


def _active_locked_test_runtime(
) -> tuple[_LockedTestRuntimeBinding, str, str] | None:
    state = _ACTIVE_PYTEST_FAILURE_STATE
    if (
        state is None
        or state.locked_runtime is None
        or state.locked_runtime_document is None
        or state.locked_runtime_sha256 is None
        or state.original_directory is None
    ):
        return None
    binding = state.locked_runtime
    try:
        if (
            ROOT.resolve(strict=True) != binding.source_root
            or state.original_directory != binding.source_root
            or Path.cwd().resolve(strict=True) != binding.repository_root
            or hashlib.sha256(state.locked_runtime_document.encode("utf-8")).hexdigest()
            != state.locked_runtime_sha256
        ):
            raise CoverageGateError("active locked pytest runtime differs")
        _assert_locked_tool_binding(binding)
    except OSError as exc:
        raise CoverageGateError("active locked pytest runtime is unavailable") from exc
    return (
        binding,
        state.locked_runtime_document,
        state.locked_runtime_sha256,
    )


def _coverage_test_repository_binding(binding: _CoverageRuntimeBinding) -> str:
    identity = binding.root_identity
    return json.dumps(
        {
            "schema_version": 1,
            "repository": str(binding.repository_root),
            "commit_oid": binding.commit_oid,
            "tree_oid": binding.tree_oid,
            "root_identity": _identity_document(identity),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _locked_test_repository_binding(binding: _LockedTestRuntimeBinding) -> str:
    return json.dumps(
        {
            "schema_version": 1,
            "repository": str(binding.repository_root),
            "commit_oid": binding.commit_oid,
            "tree_oid": binding.tree_oid,
            "root_identity": _identity_document(binding.root_identity),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _coverage_scan_failure() -> AssertionError:
    return AssertionError("coverage test repository binding is invalid")


def _coverage_scan_directory(value: object) -> Path:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > 16_384
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise _coverage_scan_failure()
    try:
        candidate = Path(value)
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        raise _coverage_scan_failure() from exc
    if (
        not candidate.is_absolute()
        or str(resolved) != value
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
    ):
        raise _coverage_scan_failure()
    return resolved


def _coverage_scan_identity(value: object) -> _PathIdentity:
    keys = (
        "device",
        "inode",
        "size",
        "modified_ns",
        "changed_ns",
        "mode",
    )
    if not isinstance(value, dict) or set(value) != set(keys):
        raise _coverage_scan_failure()
    values = tuple(value[key] for key in keys)
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 0
        for item in values
    ):
        raise _coverage_scan_failure()
    return _PathIdentity(*values)


def _coverage_scan_request_document(source: bytes) -> _CoverageScanRequest:
    if not source or len(source) > MAX_BOUND_SCAN_REQUEST_BYTES:
        raise _coverage_scan_failure()
    try:
        document = json.loads(
            source,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError, UnicodeError, ValueError) as exc:
        raise _coverage_scan_failure() from exc
    expected = {
        "schema_version",
        "source_root",
        "repository",
        "outputs_root",
        "commit_oid",
        "tree_oid",
        "root_identity",
        "tree_mode",
        "build_distributions",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise _coverage_scan_failure()
    schema_version = document["schema_version"]
    commit_oid = document["commit_oid"]
    tree_oid = document["tree_oid"]
    tree_mode = document["tree_mode"]
    build_distributions = document["build_distributions"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
        or not isinstance(commit_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", commit_oid) is None
        or not isinstance(tree_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", tree_oid) is None
        or not isinstance(tree_mode, str)
        or tree_mode not in {"working-pre-cutover", "candidate", "final"}
        or not isinstance(build_distributions, bool)
    ):
        raise _coverage_scan_failure()
    return _CoverageScanRequest(
        source_root=_coverage_scan_directory(document["source_root"]),
        repository=_coverage_scan_directory(document["repository"]),
        outputs_root=_coverage_scan_directory(document["outputs_root"]),
        commit_oid=commit_oid,
        tree_oid=tree_oid,
        root_identity=_coverage_scan_identity(document["root_identity"]),
        tree_mode=tree_mode,
        build_distributions=build_distributions,
    )


def _coverage_scan_binding_document(source: str) -> dict[str, object]:
    if type(source) is not str:
        raise _coverage_scan_failure()
    try:
        encoded = source.encode("utf-8")
        if not encoded or len(encoded) > 16 * 1024:
            raise ValueError("binding size")
        document = json.loads(
            encoded,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError, UnicodeError, ValueError) as exc:
        raise _coverage_scan_failure() from exc
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "repository",
        "commit_oid",
        "tree_oid",
        "root_identity",
    }:
        raise _coverage_scan_failure()
    schema_version = document["schema_version"]
    commit_oid = document["commit_oid"]
    tree_oid = document["tree_oid"]
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
        or not isinstance(commit_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", commit_oid) is None
        or not isinstance(tree_oid, str)
        or re.fullmatch(r"[0-9a-f]{40}", tree_oid) is None
    ):
        raise _coverage_scan_failure()
    repository = _coverage_scan_directory(document["repository"])
    identity = _coverage_scan_identity(document["root_identity"])
    return {
        "schema_version": 1,
        "repository": str(repository),
        "commit_oid": commit_oid,
        "tree_oid": tree_oid,
        "root_identity": {
            "device": identity.device,
            "inode": identity.inode,
            "size": identity.size,
            "modified_ns": identity.modified_ns,
            "changed_ns": identity.changed_ns,
            "mode": identity.mode,
        },
    }


def _validate_coverage_scan_repository(request: _CoverageScanRequest) -> None:
    repository = request.repository
    try:
        before = repository.lstat()
        top_level_source = _bound_git_output(
            "rev-parse",
            "--show-toplevel",
            maximum_bytes=32 * 1024,
            repository=repository,
        )
        top_level = Path(top_level_source.decode("utf-8").strip()).resolve(strict=True)
        head = _bound_git_oid("HEAD", repository=repository)
        head_tree = _bound_git_oid("HEAD^{tree}", repository=repository)
        committed_tree = _bound_git_oid(
            f"{request.commit_oid}^{{tree}}",
            repository=repository,
        )
        _assert_default_git_index(repository=repository)
        status = _bound_git_output(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            maximum_bytes=1024 * 1024,
            repository=repository,
        )
        after = repository.lstat()
    except (CoverageGateError, OSError, RuntimeError, UnicodeError) as exc:
        raise _coverage_scan_failure() from exc
    if (
        _identity(before) != request.root_identity
        or _identity(after) != request.root_identity
        or top_level != repository
        or head != request.commit_oid
        or head_tree != request.tree_oid
        or committed_tree != request.tree_oid
        or status != b""
    ):
        raise _coverage_scan_failure()


def _coverage_scan_canonical_path(raw: bytes) -> str:
    try:
        value = raw.decode("utf-8")
    except UnicodeError as exc:
        raise _coverage_scan_failure() from exc
    pure = Path(value)
    parts = value.split("/")
    if (
        not value
        or "\\" in value
        or value.startswith("/")
        or pure.is_absolute()
        or "/".join(parts) != value
        or not all(_is_canonical_repository_component(part) for part in parts)
    ):
        raise _coverage_scan_failure()
    return value


def _coverage_scan_records(source: bytes) -> list[bytes]:
    if not source or not source.endswith(b"\0"):
        raise _coverage_scan_failure()
    return source[:-1].split(b"\0")


def _coverage_scan_inventory(
    request: _CoverageScanRequest,
) -> dict[str, tuple[str, str]]:
    try:
        tree_source = _bound_git_output(
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            request.commit_oid,
            maximum_bytes=64 * 1024 * 1024,
            repository=request.repository,
        )
        index_source = _bound_git_output(
            "ls-files",
            "-s",
            "-z",
            "--full-name",
            maximum_bytes=64 * 1024 * 1024,
            repository=request.repository,
        )
    except (CoverageGateError, OSError, RuntimeError, UnicodeError) as exc:
        raise _coverage_scan_failure() from exc
    tree: dict[str, tuple[str, str]] = {}
    tree_folded: set[str] = set()
    for record in _coverage_scan_records(tree_source):
        try:
            header, raw_path = record.split(b"\t", 1)
            mode, object_type, raw_oid = header.split(b" ")
            path = _coverage_scan_canonical_path(raw_path)
            oid = raw_oid.decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise _coverage_scan_failure() from exc
        folded = path.casefold()
        if (
            mode not in {b"100644", b"100755"}
            or object_type != b"blob"
            or re.fullmatch(r"[0-9a-f]{40}", oid) is None
            or path in tree
            or folded in tree_folded
        ):
            raise _coverage_scan_failure()
        tree[path] = (mode.decode("ascii"), oid)
        tree_folded.add(folded)
    index: dict[str, tuple[str, str]] = {}
    index_folded: set[str] = set()
    for record in _coverage_scan_records(index_source):
        try:
            header, raw_path = record.split(b"\t", 1)
            mode, raw_oid, stage = header.split(b" ")
            path = _coverage_scan_canonical_path(raw_path)
            oid = raw_oid.decode("ascii")
        except (UnicodeError, ValueError) as exc:
            raise _coverage_scan_failure() from exc
        folded = path.casefold()
        if (
            mode not in {b"100644", b"100755"}
            or re.fullmatch(r"[0-9a-f]{40}", oid) is None
            or stage != b"0"
            or path in index
            or folded in index_folded
        ):
            raise _coverage_scan_failure()
        index[path] = (mode.decode("ascii"), oid)
        index_folded.add(folded)
    if not tree or index != tree:
        raise _coverage_scan_failure()
    return tree


def _coverage_scan_blob_oid(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data,
        usedforsecurity=False,
    ).hexdigest()


def _validate_coverage_scan_read(
    request: _CoverageScanRequest,
    inventory: Mapping[str, tuple[str, str]],
    root: Path,
    relative: Any,
    data: bytes,
) -> None:
    try:
        read_root = Path(root).resolve(strict=True)
        normalized = relative.as_posix()
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _coverage_scan_failure() from exc
    if read_root != request.repository:
        return
    expected = inventory.get(normalized)
    if expected is None:
        raise _coverage_scan_failure()
    mode, oid = expected
    literal_oid = _coverage_scan_blob_oid(data)
    without_crlf = data.replace(b"\r\n", b"")
    exact_crlf_only = (
        b"\r\n" in data
        and b"\r" not in without_crlf
        and b"\n" not in without_crlf
    )
    normalized_eol_oid = ""
    if exact_crlf_only:
        normalized_eol_oid = _coverage_scan_blob_oid(data.replace(b"\r\n", b"\n"))
    try:
        metadata = request.repository.joinpath(*relative.parts).lstat()
    except (AttributeError, OSError, TypeError) as exc:
        raise _coverage_scan_failure() from exc
    if (
        (literal_oid != oid and normalized_eol_oid != oid)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or (
            os.name != "nt"
            and ("100755" if metadata.st_mode & 0o111 else "100644") != mode
        )
    ):
        raise _coverage_scan_failure()


def _execute_coverage_scan_child(request: _CoverageScanRequest) -> dict[str, object]:
    expected_source_root = ROOT.resolve(strict=True)
    expected_controller = expected_source_root / "scripts" / "run_coverage_gate.py"
    if (
        request.source_root != expected_source_root
        or Path(__file__).resolve(strict=True) != expected_controller
    ):
        raise _coverage_scan_failure()
    _validate_coverage_scan_repository(request)
    inventory = _coverage_scan_inventory(request)
    try:
        import hsconfig.release_gate as release_gate_module
    except (ImportError, RuntimeError) as exc:
        raise _coverage_scan_failure() from exc
    real_read = release_gate_module._secure_read_bytes

    def bound_read(root: Path, relative: Any, **kwargs: object) -> bytes:
        data = real_read(root, relative, **kwargs)
        _validate_coverage_scan_read(request, inventory, root, relative, data)
        return data

    release_gate_module._secure_read_bytes = bound_read
    try:
        result = release_gate_module.scan_publishable_content(
            repository=request.repository,
            outputs_root=request.outputs_root,
            tree_mode=request.tree_mode,
            build_distributions=request.build_distributions,
        )
    finally:
        release_gate_module._secure_read_bytes = real_read
        _validate_coverage_scan_repository(request)
    return _validate_coverage_scan_result(result)


def _validate_coverage_scan_result(value: object) -> dict[str, object]:
    expected = {
        "passed",
        "violations",
        "tracked_files_scanned",
        "current_packages_scanned",
        "distribution_artifacts_scanned",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise _coverage_scan_failure()
    passed = value["passed"]
    violations = value["violations"]
    counts = tuple(value[key] for key in expected if key.endswith("_scanned"))
    if (
        not isinstance(passed, bool)
        or not isinstance(violations, list)
        or any(not isinstance(row, str) or not row for row in violations)
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in counts
        )
        or passed is bool(violations)
        or violations != sorted(set(violations))
    ):
        raise _coverage_scan_failure()
    return {
        "passed": passed,
        "violations": violations,
        "tracked_files_scanned": value["tracked_files_scanned"],
        "current_packages_scanned": value["current_packages_scanned"],
        "distribution_artifacts_scanned": value["distribution_artifacts_scanned"],
    }


def _coverage_scan_child_main() -> int:
    try:
        source = sys.stdin.buffer.read(MAX_BOUND_SCAN_REQUEST_BYTES + 1)
        request = _coverage_scan_request_document(source)
        result = _execute_coverage_scan_child(request)
        envelope: dict[str, object] = {"schema_version": 1, "result": result}
        output = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8") + b"\n"
        if len(output) > MAX_BOUND_SCAN_RESPONSE_BYTES:
            raise _coverage_scan_failure()
    except Exception:
        sys.stdout.write('{"error":"coverage test repository binding is invalid","schema_version":1}\n')
        return 2
    sys.stdout.buffer.write(output)
    return 0


def _run_bound_coverage_scan(
    *,
    binding_json: str,
    outputs_root: Path,
    tree_mode: str,
    build_distributions: bool,
) -> dict[str, object]:
    if (
        type(outputs_root) is not type(Path())
        or type(tree_mode) is not str
        or tree_mode not in {"working-pre-cutover", "candidate", "final"}
        or not isinstance(build_distributions, bool)
    ):
        raise _coverage_scan_failure()
    binding = _coverage_scan_binding_document(binding_json)
    source_root = ROOT.resolve(strict=True)
    outputs = _coverage_scan_directory(str(outputs_root))
    request = {
        **binding,
        "source_root": str(source_root),
        "outputs_root": str(outputs),
        "tree_mode": tree_mode,
        "build_distributions": build_distributions,
    }
    source = json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(source) > MAX_BOUND_SCAN_REQUEST_BYTES:
        raise _coverage_scan_failure()
    controller = source_root / "scripts" / "run_coverage_gate.py"
    try:
        controller_metadata = controller.lstat()
        if (
            controller.resolve(strict=True) != controller
            or not stat.S_ISREG(controller_metadata.st_mode)
            or stat.S_ISLNK(controller_metadata.st_mode)
            or _is_reparse(controller_metadata)
        ):
            raise _coverage_scan_failure()
    except OSError as exc:
        raise _coverage_scan_failure() from exc
    environment = os.environ.copy()
    for key in tuple(environment):
        upper = key.upper()
        if upper in _BOOTSTRAP_AUTHORITY_VARIABLES or upper.startswith("PYTHON"):
            environment.pop(key, None)
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
            "PYTHONPATH": os.pathsep.join(
                (str(source_root / "src"), str(source_root))
            ),
        }
    )
    active_runtime = _active_locked_test_runtime()
    locked_runtime = active_runtime[0] if active_runtime is not None else None
    interpreter = (
        locked_runtime.interpreter
        if locked_runtime is not None
        else Path(sys.executable).resolve(strict=True)
    )
    try:
        bounded = _run_bounded_process(
            (str(interpreter), str(controller), "--coverage-bound-scan-child"),
            cwd=source_root,
            env=environment,
            timeout=BOUND_SCAN_TIMEOUT_SECONDS,
            stdin_data=source,
            launcher=interpreter,
            locked_runtime=locked_runtime,
        )
    except (CoverageGateError, OSError, RuntimeError, ValueError) as exc:
        raise _coverage_scan_failure() from exc
    if (
        bounded.timed_out
        or bounded.completed.returncode != 0
        or bounded.stdout.error is not None
        or bounded.stderr.error is not None
        or bounded.stdout.total > MAX_BOUND_SCAN_RESPONSE_BYTES
        or bounded.stdout.truncated
        or len(bounded.stdout.tail) != bounded.stdout.total
        or bounded.stderr.total != 0
    ):
        raise _coverage_scan_failure()
    try:
        output = bytes(bounded.stdout.tail).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _coverage_scan_failure() from exc
    if output.count("\n") != 1 or not output.endswith("\n") or "\r" in output:
        raise _coverage_scan_failure()
    try:
        envelope = json.loads(
            output,
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise _coverage_scan_failure() from exc
    if (
        not isinstance(envelope, dict)
        or set(envelope) != {"schema_version", "result"}
        or not isinstance(envelope["schema_version"], int)
        or isinstance(envelope["schema_version"], bool)
        or envelope["schema_version"] != 1
    ):
        raise _coverage_scan_failure()
    return _validate_coverage_scan_result(envelope["result"])


@contextmanager
def isolated_coverage_environment(
    runtime_binding: _CoverageRuntimeBinding | None = None,
) -> Iterator[CoverageRun]:
    active_locked_runtime = (
        None if runtime_binding is not None else _active_locked_test_runtime()
    )
    forbidden_roots: list[Path] = []
    if runtime_binding is not None:
        forbidden_roots.append(runtime_binding.repository_root)
    elif active_locked_runtime is not None:
        forbidden_roots.append(active_locked_runtime[0].repository_root)
    forbidden_root_tuple = tuple(forbidden_roots)
    temporary_root = _validated_temporary_root(
        Path(tempfile.gettempdir()),
        label="temporary root",
        forbidden_roots=forbidden_root_tuple,
    )
    temporary_root_identity = _coverage_directory_identity(temporary_root)
    pytest_temporary_parent = _pytest_temporary_parent(
        temporary_root,
        forbidden_roots=forbidden_root_tuple,
    )
    pytest_temporary_parent_identity = (
        temporary_root_identity
        if pytest_temporary_parent == temporary_root
        else _coverage_directory_identity(pytest_temporary_parent)
    )
    run_root: Path | None = None
    run_identity: tuple[int, int] | None = None
    pytest_temp_root: Path | None = None
    pytest_temp_identity: tuple[int, int] | None = None
    body_error: BaseException | None = None
    try:
        run_root, run_identity = _create_owned_directory(
            temporary_root,
            prefix="hsconfig-coverage-run-",
            label="coverage run directory",
        )
        environment = os.environ.copy()
        for key in tuple(environment):
            upper = key.upper()
            if upper in _BOOTSTRAP_AUTHORITY_VARIABLES or upper.startswith(
                ("COVERAGE_", "HYPOTHESIS_", "PYTEST_", "PYTHON")
            ):
                environment.pop(key, None)
        coverage_data = run_root / ".coverage"
        coverage_json = run_root / "coverage.json"
        failure_sideband = run_root / PYTEST_FAILURE_SIDEBAND_NAME
        sideband_flags = (
            os.O_CREAT
            | os.O_EXCL
            | os.O_WRONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        sideband_descriptor = os.open(failure_sideband, sideband_flags, 0o600)
        try:
            sideband_metadata = os.fstat(sideband_descriptor)
        finally:
            os.close(sideband_descriptor)
        if (
            not stat.S_ISREG(sideband_metadata.st_mode)
            or getattr(sideband_metadata, "st_nlink", 1) != 1
        ):
            raise CoverageGateError("pytest failure sideband setup failed")
        failure_sideband_identity = (
            sideband_metadata.st_dev,
            sideband_metadata.st_ino,
        )
        pytest_temp_root, pytest_temp_identity = _create_owned_directory(
            pytest_temporary_parent,
            prefix=PYTEST_TEMP_PREFIX,
            label="pytest temporary directory",
        )
        if _windows_host() and not _windows_pytest_path_within_budget(
            pytest_temp_root.parent
        ):
            raise CoverageGateError("pytest temporary path exceeds Windows budget")
        hypothesis_storage = run_root / "hypothesis"
        hypothesis_storage.mkdir()
        environment.update(
            {
                "COVERAGE_FILE": str(coverage_data),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTHONSAFEPATH": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTEST_PLUGINS": "pytest_cov.plugin,_hypothesis_pytestplugin",
                "PYTEST_DEBUG_TEMPROOT": str(pytest_temp_root),
                "HYPOTHESIS_STORAGE_DIRECTORY": str(hypothesis_storage),
            }
        )
        locked_test_runtime: _LockedTestRuntimeBinding | None = None
        if runtime_binding is not None:
            locked_document, locked_test_runtime = _locked_test_runtime_document(
                runtime_binding
            )
            locked_document_sha256 = hashlib.sha256(
                locked_document.encode("utf-8")
            ).hexdigest()
            environment["PYTHONPATH"] = os.pathsep.join(
                str(path) for path in runtime_binding.pythonpath
            )
            environment[_COVERAGE_TEST_REPOSITORY_BINDING] = (
                _coverage_test_repository_binding(runtime_binding)
            )
            environment[_LOCKED_TEST_RUNTIME_BINDING] = locked_document
            environment[_LOCKED_TEST_RUNTIME_SHA256] = locked_document_sha256
        elif active_locked_runtime is not None:
            (
                locked_test_runtime,
                locked_document,
                locked_document_sha256,
            ) = active_locked_runtime
            environment["PYTHONPATH"] = str(
                locked_test_runtime.build_backend_root
            )
            environment[_COVERAGE_TEST_REPOSITORY_BINDING] = (
                _locked_test_repository_binding(locked_test_runtime)
            )
            environment[_LOCKED_TEST_RUNTIME_BINDING] = locked_document
            environment[_LOCKED_TEST_RUNTIME_SHA256] = locked_document_sha256
        if locked_test_runtime is not None:
            environment["VIRTUAL_ENV"] = str(locked_test_runtime.environment_root)
            environment["PATH"] = _closed_locked_test_path(locked_test_runtime)
        yield CoverageRun(
            run_root=run_root,
            run_identity=run_identity,
            pytest_temp_root=pytest_temp_root,
            pytest_temp_identity=pytest_temp_identity,
            coverage_data=coverage_data,
            coverage_json=coverage_json,
            failure_sideband=failure_sideband,
            failure_sideband_identity=failure_sideband_identity,
            environment=environment,
            locked_test_runtime=locked_test_runtime,
        )
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        cleanup_errors: list[BaseException] = []
        if pytest_temp_root is not None and pytest_temp_identity is not None:
            try:
                _cleanup_owned_run_root(
                    pytest_temporary_parent,
                    pytest_temp_root,
                    pytest_temp_identity,
                    expected_temporary_root_identity=(
                        pytest_temporary_parent_identity
                    ),
                )
            except BaseException as exc:
                cleanup_errors.append(exc)
        if run_root is not None and run_identity is not None:
            try:
                _cleanup_owned_run_root(
                    temporary_root,
                    run_root,
                    run_identity,
                    expected_temporary_root_identity=temporary_root_identity,
                )
            except BaseException as exc:
                cleanup_errors.append(exc)
        if cleanup_errors:
            if body_error is not None:
                for cleanup_error in cleanup_errors:
                    body_error.add_note(
                        "additional coverage cleanup failure: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
            else:
                primary = cleanup_errors[0]
                for additional in cleanup_errors[1:]:
                    primary.add_note(
                        "additional coverage cleanup failure: "
                        f"{type(additional).__name__}"
                    )
                raise primary


def _canonical_full_coverage_paths(
    test_root: Path,
    source_inventory: _RuntimeSourceInventory,
) -> tuple[Path, ...]:
    if type(test_root) is not type(Path()) or not isinstance(source_inventory, tuple):
        raise CoverageGateError("full coverage inventory is invalid")
    inventory_paths: list[str] = []
    for row in source_inventory:
        if (
            type(row) is not tuple
            or len(row) != 3
            or any(type(value) is not str for value in row)
        ):
            raise CoverageGateError("full coverage inventory is invalid")
        inventory_paths.append(row[0])
    if len(inventory_paths) != len(set(inventory_paths)):
        raise CoverageGateError("full coverage inventory is invalid")
    selected_relatives = tuple(
        sorted(
            relative
            for relative in inventory_paths
            if _SAFE_PYTEST_TEST_PATH.fullmatch(relative)
            and PurePosixPath(relative).name.startswith("test_")
        )
    )
    if not selected_relatives:
        raise CoverageGateError("full coverage inventory is incomplete")
    try:
        root = test_root.resolve(strict=True)
        root_metadata = test_root.lstat()
    except OSError as exc:
        raise CoverageGateError("full coverage root is unavailable") from exc
    if (
        root != test_root
        or not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or _is_reparse(root_metadata)
    ):
        raise CoverageGateError("full coverage root is unsafe")
    selected: list[Path] = []
    for relative in selected_relatives:
        path = test_root.joinpath(*relative.split("/"))
        try:
            metadata = path.lstat()
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise CoverageGateError("full coverage source is unavailable") from exc
        if (
            resolved != path
            or root not in resolved.parents
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
            or getattr(metadata, "st_nlink", 1) not in {0, 1}
        ):
            raise CoverageGateError("full coverage source is unsafe")
        selected.append(path)
    return tuple(selected)


def _pytest_coverage_command(
    coverage_json: Path,
    failure_sideband: Path,
    *,
    interpreter: Path,
    test_root: Path,
    selected_tests: tuple[Path, ...] | None = None,
) -> tuple[str, ...]:
    targets = (
        (test_root / "tests",)
        if selected_tests is None
        else selected_tests
    )
    if not targets or any(type(path) is not type(Path()) for path in targets):
        raise CoverageGateError("pytest coverage target set is invalid")
    return (
        str(interpreter),
        "-m",
        "pytest",
        "--import-mode=importlib",
        f"--rootdir={test_root}",
        "-c",
        str(test_root / "pyproject.toml"),
        "-o",
        f"pythonpath={shlex.join([str(ROOT / 'src')])}",
        "-o",
        "tmp_path_retention_policy=failed",
        f"--cov={ROOT / 'src' / 'hsconfig'}",
        "--cov-branch",
        f"--cov-config={ROOT / 'pyproject.toml'}",
        "--cov-fail-under=0",
        f"--cov-report=json:{coverage_json}",
        "--cov-report=term-missing",
        "-p",
        "no:cacheprovider",
        "-p",
        "scripts.run_coverage_gate",
        f"{_PYTEST_FAILURE_SIDEBAND_OPTION}={failure_sideband}",
        *(str(path) for path in targets),
    )


def _load_pytest_failure_sideband(
    run_root: Path,
    failure_sideband: Path,
    expected_run_identity: tuple[int, int],
    expected_sideband_identity: tuple[int, int],
    *,
    allowed_identities: frozenset[_PytestTestIdentity] | None = None,
    allowed_collection_paths: frozenset[str] | None = None,
) -> _PytestFailureSideband:
    def unavailable(status: _PytestFailureSidebandStatus) -> _PytestFailureSideband:
        return _PytestFailureSideband(
            status=status,
            identities=(),
            truncated=False,
        )

    try:
        sideband_metadata = failure_sideband.lstat()
    except FileNotFoundError:
        return unavailable(_PytestFailureSidebandStatus.MISSING)
    except OSError:
        return unavailable(_PytestFailureSidebandStatus.IO_ERROR)
    try:
        if not isinstance(allowed_identities, frozenset):
            raise CoverageGateError("pytest failure identity vocabulary is unavailable")
        if allowed_collection_paths is None:
            allowed_collection_paths = frozenset(
                path for path, _class_name, _function_name in allowed_identities
            )
        if (
            not isinstance(allowed_collection_paths, frozenset)
            or any(
                not isinstance(path, str)
                or len(path) > 240
                or _SAFE_PYTEST_TEST_PATH.fullmatch(path) is None
                for path in allowed_collection_paths
            )
        ):
            raise CoverageGateError("pytest collection vocabulary is unavailable")
        if _coverage_directory_identity(run_root) != expected_run_identity:
            raise CoverageGateError("pytest failure sideband root changed")
        root = run_root.resolve(strict=True)
        if (
            failure_sideband != run_root / PYTEST_FAILURE_SIDEBAND_NAME
            or failure_sideband.parent.resolve(strict=True) != root
        ):
            raise CoverageGateError("pytest failure sideband path is invalid")
        if (
            not stat.S_ISREG(sideband_metadata.st_mode)
            or stat.S_ISLNK(sideband_metadata.st_mode)
            or _is_reparse(sideband_metadata)
            or getattr(sideband_metadata, "st_nlink", 1) != 1
            or sideband_metadata.st_size > MAX_PYTEST_FAILURE_SIDEBAND_BYTES
            or (sideband_metadata.st_dev, sideband_metadata.st_ino)
            != expected_sideband_identity
        ):
            raise CoverageGateError("pytest failure sideband is invalid")
    except (CoverageGateError, OSError, TypeError, ValueError):
        return unavailable(_PytestFailureSidebandStatus.INVALID_BINDING)
    try:
        source, metadata = _read_bound_regular_file(
            failure_sideband,
            maximum_bytes=MAX_PYTEST_FAILURE_SIDEBAND_BYTES,
            error_type=CoverageGateError,
            label="pytest failure sideband",
        )
    except OSError:
        return unavailable(_PytestFailureSidebandStatus.IO_ERROR)
    except CoverageGateError as exc:
        status = (
            _PytestFailureSidebandStatus.IO_ERROR
            if isinstance(exc.__cause__, OSError)
            else _PytestFailureSidebandStatus.INVALID_BINDING
        )
        return unavailable(status)
    try:
        if (
            getattr(metadata, "st_nlink", 1) != 1
            or (metadata.st_dev, metadata.st_ino) != expected_sideband_identity
            or _coverage_directory_identity(run_root) != expected_run_identity
            or not source.endswith(b"\n")
            or source.count(b"\n") != 1
            or b"\r" in source
        ):
            raise CoverageGateError("pytest failure sideband is invalid")
    except (CoverageGateError, OSError, TypeError, ValueError):
        return unavailable(_PytestFailureSidebandStatus.INVALID_BINDING)
    try:
        document = json.loads(
            source.decode("utf-8"),
            object_pairs_hook=_closed_object,
            parse_constant=_reject_constant,
        )
        if (
            not isinstance(document, dict)
            or set(document)
            != {"schema_version", "recorder_status", "failures", "truncated"}
            or not isinstance(document["schema_version"], int)
            or isinstance(document["schema_version"], bool)
            or document["schema_version"] != 1
            or document["recorder_status"] not in {"available", "unavailable"}
            or not isinstance(document["failures"], list)
            or len(document["failures"]) > MAX_PYTEST_FAILURE_IDENTITIES
            or not isinstance(document["truncated"], bool)
            or (
                document["truncated"]
                and len(document["failures"]) != MAX_PYTEST_FAILURE_IDENTITIES
            )
        ):
            raise CoverageGateError("pytest failure sideband schema is invalid")
        if document["recorder_status"] == "unavailable":
            if document["failures"] or document["truncated"]:
                raise CoverageGateError("pytest failure sideband schema is invalid")
            return unavailable(
                _PytestFailureSidebandStatus.RECORDER_UNAVAILABLE
            )
        identities: list[str] = []
        seen: set[tuple[object, ...]] = set()
        for failure in document["failures"]:
            if not isinstance(failure, dict):
                raise CoverageGateError("pytest failure sideband record is invalid")
            if set(failure) == {"path", "phase"}:
                path = failure["path"]
                if (
                    failure["phase"] != "collection"
                    or not isinstance(path, str)
                    or len(path) > 240
                    or _SAFE_PYTEST_TEST_PATH.fullmatch(path) is None
                    or path not in allowed_collection_paths
                ):
                    raise CoverageGateError(
                        "pytest failure sideband collection record is invalid"
                    )
                identity_key = (path, "collection")
                if identity_key in seen:
                    raise CoverageGateError(
                        "pytest failure sideband contains duplicates"
                    )
                seen.add(identity_key)
                identities.append(f"{path} phase=collection")
                continue
            if set(failure) != {
                "path",
                "class",
                "function",
                "parameter",
                "phase",
            }:
                raise CoverageGateError("pytest failure sideband record is invalid")
            path = failure["path"]
            class_name = failure["class"]
            function_name = failure["function"]
            parameter = failure["parameter"]
            phase = failure["phase"]
            if (
                not isinstance(path, str)
                or len(path) > 240
                or _SAFE_PYTEST_TEST_PATH.fullmatch(path) is None
                or (
                    class_name is not None
                    and (
                        not isinstance(class_name, str)
                        or _SAFE_PYTEST_IDENTIFIER.fullmatch(class_name) is None
                    )
                )
                or not isinstance(function_name, str)
                or _SAFE_PYTEST_IDENTIFIER.fullmatch(function_name) is None
                or phase not in _PYTEST_FAILURE_PHASES
            ):
                raise CoverageGateError("pytest failure sideband record is unsafe")
            if (path, class_name, function_name) not in allowed_identities:
                raise CoverageGateError(
                    "pytest failure sideband record is not source-backed"
                )
            ordinal: int | None = None
            total: int | None = None
            if parameter is not None:
                if (
                    not isinstance(parameter, dict)
                    or set(parameter) != {"ordinal", "total"}
                    or not isinstance(parameter["ordinal"], int)
                    or isinstance(parameter["ordinal"], bool)
                    or not isinstance(parameter["total"], int)
                    or isinstance(parameter["total"], bool)
                    or not 1 <= parameter["ordinal"] <= parameter["total"] <= 1_000_000
                ):
                    raise CoverageGateError(
                        "pytest failure sideband parameter is invalid"
                    )
                ordinal = parameter["ordinal"]
                total = parameter["total"]
            identity_key = (
                path,
                class_name,
                function_name,
                ordinal,
                total,
                phase,
            )
            if identity_key in seen:
                raise CoverageGateError("pytest failure sideband contains duplicates")
            seen.add(identity_key)
            node = f"{path}::{function_name}"
            if class_name is not None:
                node = f"{path}::{class_name}::{function_name}"
            parameter_suffix = (
                "" if ordinal is None else f" parameter={ordinal}/{total}"
            )
            identities.append(f"{node}{parameter_suffix} phase={phase}")
        return _PytestFailureSideband(
            status=_PytestFailureSidebandStatus.VALID,
            identities=tuple(identities),
            truncated=document["truncated"],
        )
    except (
        CoverageGateError,
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        return unavailable(_PytestFailureSidebandStatus.INVALID_SCHEMA)


def _emit_pytest_failure_identities(
    report: _PytestFailureSideband,
) -> None:
    if report.status is not _PytestFailureSidebandStatus.VALID:
        messages = {
            _PytestFailureSidebandStatus.RECORDER_UNAVAILABLE: (
                "pytest failure recorder unavailable"
            ),
            _PytestFailureSidebandStatus.MISSING: "pytest failure sideband missing",
            _PytestFailureSidebandStatus.INVALID_BINDING: (
                "pytest failure sideband binding invalid"
            ),
            _PytestFailureSidebandStatus.INVALID_SCHEMA: (
                "pytest failure sideband schema invalid"
            ),
            _PytestFailureSidebandStatus.IO_ERROR: "pytest failure sideband read failed",
        }
        print(messages[report.status], file=sys.stderr)
        return
    if not report.identities:
        print(
            "pytest failure identity: session-level failure; no node identities",
            file=sys.stderr,
        )
        return
    for identity in report.identities:
        print(f"pytest failure identity: {identity}", file=sys.stderr)
    if report.truncated:
        print(
            f"pytest failure identities truncated at {MAX_PYTEST_FAILURE_IDENTITIES}",
            file=sys.stderr,
        )


def _checker_command(*, interpreter: Path) -> tuple[str, ...]:
    return (str(interpreter), "-c", CHECKER_BRIDGE)


def _coverage_report_identity(
    run_root: Path,
    coverage_json: Path,
    expected_run_identity: tuple[int, int] | None = None,
) -> CoverageReportIdentity:
    try:
        run_metadata = run_root.lstat()
    except OSError as exc:
        raise CoverageGateError("coverage run directory cannot be inspected") from exc
    actual_run_identity = _coverage_directory_identity(run_root)
    if expected_run_identity is not None and actual_run_identity != expected_run_identity:
        raise CoverageGateError("coverage run directory changed")
    try:
        root = run_root.resolve(strict=True)
        if coverage_json.parent.resolve(strict=True) != root:
            raise CoverageGateError("coverage report is outside its run directory")
    except OSError as exc:
        raise CoverageGateError("coverage report cannot be validated") from exc
    source, metadata = _read_bound_regular_file(
        coverage_json,
        maximum_bytes=MAX_COVERAGE_JSON_BYTES,
        error_type=CoverageGateError,
        label="coverage report",
    )
    if _coverage_directory_identity(run_root) != actual_run_identity:
        raise CoverageGateError("coverage run directory changed")
    try:
        run_after = run_root.lstat()
    except OSError as exc:
        raise CoverageGateError("coverage run directory cannot be inspected") from exc
    if _identity(run_after) != _identity(run_metadata):
        raise CoverageGateError("coverage run directory changed")
    return CoverageReportIdentity(
        device=metadata.st_dev,
        inode=metadata.st_ino,
        size=metadata.st_size,
        modified_ns=metadata.st_mtime_ns,
        changed_ns=metadata.st_ctime_ns,
        run_modified_ns=run_metadata.st_mtime_ns,
        run_changed_ns=run_metadata.st_ctime_ns,
        digest=hashlib.sha256(source).hexdigest(),
        content=source,
    )


def _assert_coverage_report_unchanged(
    run_root: Path,
    coverage_json: Path,
    expected: CoverageReportIdentity,
    expected_run_identity: tuple[int, int] | None = None,
) -> None:
    if _coverage_report_identity(
        run_root,
        coverage_json,
        expected_run_identity,
    ) != expected:
        raise CoverageGateError("coverage report changed during checker execution")


def _write_stdin(stream: Any, payload: bytes) -> None:
    try:
        stream.write(payload)
        stream.flush()
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        try:
            stream.close()
        except (OSError, ValueError):
            pass


def _run_bounded_process(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    stdin_data: bytes | None = None,
    launcher: Path | None = None,
    locked_runtime: _LockedTestRuntimeBinding | None = None,
) -> _BoundedResult:
    if locked_runtime is not None:
        _assert_locked_tool_binding(locked_runtime)
        process_interpreter = locked_runtime.interpreter
        if (
            command[0] != str(process_interpreter)
            or (launcher is not None and launcher != process_interpreter)
        ):
            raise CoverageGateError("locked subprocess interpreter differs")
    else:
        process_interpreter = (
            launcher
            if launcher is not None
            else Path(sys.executable).resolve(strict=True)
        )
    platform_options: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process: subprocess.Popen[bytes] | None = None
    lease: _ProcessTreeLease | None = None
    stdout_capture = _BoundedCapture()
    stderr_capture = _BoundedCapture()
    if os.name != "nt":
        _enable_posix_subreaper()
    baseline = _linux_direct_children()
    launch_payload = (
        json.dumps(list(command), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
        + (stdin_data or b"")
    )
    threads: list[threading.Thread] = []
    started_threads: list[threading.Thread] = []
    timed_out = False
    returncode = 2
    try:
        process = subprocess.Popen(
            (
                _process_tree_gate_interpreter(process_interpreter),
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
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise CoverageGateError("coverage subprocess pipes are unavailable")
        threads = [
            threading.Thread(target=stdout_capture.drain, args=(process.stdout,), daemon=True),
            threading.Thread(target=stderr_capture.drain, args=(process.stderr,), daemon=True),
            threading.Thread(
                target=_write_stdin,
                args=(process.stdin, launch_payload),
                daemon=True,
            ),
        ]
        for thread in threads:
            thread.start()
            started_threads.append(thread)
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            returncode = 2
        finally:
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
        for thread in started_threads:
            thread.join(timeout=max(0.0, deadline - time.monotonic()))
        alive = [thread for thread in started_threads if thread.is_alive()]
        if process is not None:
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except BaseException:
                        pass
        if alive:
            raise CoverageGateError(
                "coverage subprocess transport did not terminate before hard deadline"
            )
    if locked_runtime is not None:
        _assert_locked_tool_binding(locked_runtime)
    return _BoundedResult(
        completed=subprocess.CompletedProcess(
            command,
            returncode,
            stdout=stdout_capture.text(),
            stderr=stderr_capture.text(),
        ),
        timed_out=timed_out,
        stdout=stdout_capture,
        stderr=stderr_capture,
    )


def _diagnostic_digest(label: str, capture: _BoundedCapture) -> None:
    if capture.total:
        print(
            f"{label} diagnostic bytes={capture.total} "
            f"sha256={capture.digest.hexdigest()} "
            f"truncated={str(capture.truncated).lower()}",
            file=sys.stderr,
        )


def _run_checker_bounded(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int,
    input_bytes: bytes = b"",
    locked_runtime: _LockedTestRuntimeBinding | None = None,
) -> subprocess.CompletedProcess[str]:
    bounded = _run_bounded_process(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
        stdin_data=input_bytes,
        launcher=(locked_runtime.interpreter if locked_runtime is not None else None),
        locked_runtime=locked_runtime,
    )
    _diagnostic_digest("coverage checker", bounded.stderr)
    result = bounded.completed
    if bounded.stdout.error is not None:
        return subprocess.CompletedProcess(
            command,
            2,
            stdout=_json_line(
                _failure_report("coverage checker stdout read failed", 2)
            ),
            stderr="",
        )
    if bounded.stderr.error is not None:
        return subprocess.CompletedProcess(
            command,
            2,
            stdout=_json_line(
                _failure_report("coverage checker stderr read failed", 2)
            ),
            stderr="",
        )
    if bounded.timed_out:
        return subprocess.CompletedProcess(
            command,
            2,
            stdout=_json_line(_failure_report("coverage checker timed out", 2)),
            stderr="",
        )
    if bounded.stdout.truncated:
        return subprocess.CompletedProcess(
            command,
            2,
            stdout=_json_line(
                _failure_report("coverage checker stdout exceeded limit", 2)
            ),
            stderr="",
        )
    return subprocess.CompletedProcess(
        command,
        result.returncode,
        stdout=result.stdout,
        stderr="",
    )


def _run_pytest_bounded(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
    locked_runtime: _LockedTestRuntimeBinding | None = None,
) -> _PytestResult:
    bounded = _run_bounded_process(
        command,
        cwd=cwd,
        env=env,
        timeout=PYTEST_TIMEOUT_SECONDS,
        launcher=(locked_runtime.interpreter if locked_runtime is not None else None),
        locked_runtime=locked_runtime,
    )
    _diagnostic_digest("pytest stdout", bounded.stdout)
    _diagnostic_digest("pytest stderr", bounded.stderr)
    transport_failed = (
        bounded.stdout.error is not None or bounded.stderr.error is not None
    )
    return _PytestResult(
        returncode=2 if transport_failed else bounded.completed.returncode,
        timed_out=bounded.timed_out,
    )


def main(
    *,
    test_source_inventory: _RuntimeSourceInventory | None = None,
) -> int:
    failure_phase = "runtime_binding"
    try:
        runtime_binding = _assert_runtime_matches_lock(LOCK_FILE)
        failure_phase = "source_binding"
        source_root = ROOT.resolve(strict=True)
        if runtime_binding is None:
            if test_source_inventory is None:
                raise CoverageGateError("pytest test identity source is unbound")
            source_inventory = test_source_inventory
        else:
            if (
                test_source_inventory is not None
                or not runtime_binding.pythonpath
                or runtime_binding.pythonpath[0].resolve(strict=True) != source_root
            ):
                raise CoverageGateError("pytest test identity source is unbound")
            source_inventory = runtime_binding.source_inventory
        failure_phase = "pytest_identity"
        allowed_pytest_identities = _pytest_test_identity_allowlist(
            source_root,
            source_inventory=source_inventory,
        )
        allowed_collection_paths = _pytest_collection_path_allowlist(
            source_inventory
        )
        pytest_failure: tuple[str, int] | None = None
        pytest_failure_identities: _PytestFailureSideband | None = None
        checker_result: subprocess.CompletedProcess[str] | None = None
        failure_phase = "isolation_setup"
        with isolated_coverage_environment(runtime_binding) as run:
            failure_phase = "locked_runtime"
            locked_runtime = run.locked_test_runtime
            if locked_runtime is not None:
                _assert_locked_test_runtime(locked_runtime)
            interpreter = (
                locked_runtime.interpreter
                if locked_runtime is not None
                else Path(sys.executable).resolve(strict=True)
            )
            test_root = (
                locked_runtime.repository_root
                if locked_runtime is not None
                else source_root
            )
            failure_phase = "test_selection"
            selected_tests = (
                _canonical_full_coverage_paths(test_root, source_inventory)
                if runtime_binding is not None
                else None
            )
            try:
                failure_phase = "pytest_execution"
                pytest_result = _run_pytest_bounded(
                    _pytest_coverage_command(
                        run.coverage_json,
                        run.failure_sideband,
                        interpreter=interpreter,
                        test_root=test_root,
                        selected_tests=selected_tests,
                    ),
                    cwd=(
                        locked_runtime.repository_root
                        if locked_runtime is not None
                        else ROOT
                    ),
                    env=run.environment,
                    locked_runtime=locked_runtime,
                )
            finally:
                if locked_runtime is not None:
                    primary_failure_phase = failure_phase
                    failure_phase = "pytest_post_binding"
                    _assert_locked_test_runtime(locked_runtime)
                    failure_phase = primary_failure_phase
            if pytest_result.timed_out:
                pytest_failure = ("pytest coverage execution timed out", 2)
            elif pytest_result.returncode != 0:
                pytest_failure = (
                    "pytest coverage execution failed",
                    _portable_child_returncode(pytest_result.returncode),
                )
            if pytest_failure is not None:
                failure_phase = "pytest_failure_identity"
                pytest_failure_identities = _load_pytest_failure_sideband(
                    run.run_root,
                    run.failure_sideband,
                    run.run_identity,
                    run.failure_sideband_identity,
                    allowed_identities=allowed_pytest_identities,
                    allowed_collection_paths=allowed_collection_paths,
                )
                if (
                    pytest_failure_identities.status
                    is not _PytestFailureSidebandStatus.VALID
                ):
                    pytest_failure = (pytest_failure[0], 2)
            else:
                failure_phase = "coverage_report"
                identity = _coverage_report_identity(
                    run.run_root,
                    run.coverage_json,
                    run.run_identity,
                )
                failure_phase = "coverage_checker"
                checker_result = _run_checker_bounded(
                    _checker_command(interpreter=interpreter),
                    cwd=ROOT,
                    env=run.environment,
                    timeout=CHECKER_TIMEOUT_SECONDS,
                    input_bytes=identity.content,
                    locked_runtime=locked_runtime,
                )
                failure_phase = "coverage_report_revalidation"
                _assert_coverage_report_unchanged(
                    run.run_root,
                    run.coverage_json,
                    identity,
                    run.run_identity,
                )
            failure_phase = "isolation_cleanup"
        if pytest_failure is not None:
            message, returncode = pytest_failure
            if pytest_failure_identities is None:
                raise CoverageGateError("pytest failure sideband result is unavailable")
            _emit_pytest_failure_identities(pytest_failure_identities)
            _emit_failure(message, returncode)
            return returncode
        if checker_result is None:
            raise CoverageGateError("coverage checker did not run")
        return _forward_checker_result(checker_result)
    except RuntimeLockError as exc:
        print("coverage gate runtime lock mismatch", file=sys.stderr)
        _emit_failure(
            "coverage runtime does not match project lock",
            2,
            runtime_lock_category=exc.category,
            runtime_lock_reason=(
                exc.reason
                if exc.category is RuntimeLockCategory.REPOSITORY_BINDING
                else None
            ),
        )
        return 2
    except CoverageGateError:
        print(
            f"coverage gate validation failure phase={failure_phase}",
            file=sys.stderr,
        )
        _emit_failure("coverage isolation or report validation failed", 2)
        return 2
    except Exception as exc:
        print(
            f"coverage gate subprocess error: {type(exc).__name__}",
            file=sys.stderr,
        )
        _emit_failure("coverage subprocess execution failed", 2)
        return 2


if __name__ == "__main__":
    if sys.argv[1:] == ["--coverage-bound-scan-child"]:
        raise SystemExit(_coverage_scan_child_main())
    if len(sys.argv) != 1:
        _emit_failure("usage: run_coverage_gate.py", 2)
        raise SystemExit(2)
    raise SystemExit(main())
