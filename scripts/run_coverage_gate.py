from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import ast
import csv
import base64
from dataclasses import dataclass, field
import hashlib
from importlib import metadata as importlib_metadata
import io
import json
import math
import os
from pathlib import Path
import re
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
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / f"pylock.{sys.version_info.major}.{sys.version_info.minor}.toml"
CHECKER_TIMEOUT_SECONDS = 120
PYTEST_TIMEOUT_SECONDS = 1800
CAPTURE_LIMIT = 64 * 1024
MAX_COVERAGE_JSON_BYTES = 256 * 1024 * 1024
MAX_LOCK_BYTES = 4 * 1024 * 1024
MAX_RUNTIME_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_RUNTIME_ARTIFACT_BYTES = 512 * 1024 * 1024
GLOBAL_MINIMUM = 90.0
GLOBAL_TARGET = 95.0
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


class RuntimeLockError(CoverageGateError):
    pass


@dataclass(frozen=True)
class CoverageRun:
    run_root: Path
    run_identity: tuple[int, int]
    coverage_data: Path
    coverage_json: Path
    environment: dict[str, str]


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
class _BoundedResult:
    completed: subprocess.CompletedProcess[str]
    timed_out: bool
    stdout: _BoundedCapture
    stderr: _BoundedCapture


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


def _failure_report(message: str, returncode: int) -> dict[str, object]:
    return {
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


def _json_line(document: Mapping[str, object]) -> str:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ) + "\n"


def _emit_failure(message: str, returncode: int) -> None:
    sys.stdout.write(_json_line(_failure_report(message, returncode)))


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
        raise RuntimeLockError("runtime bootstrap manifest is missing")
    manifest_path = Path(manifest_name)
    source, _ = _read_bound_regular_file(
        manifest_path,
        maximum_bytes=MAX_RUNTIME_MANIFEST_BYTES,
        error_type=RuntimeLockError,
        label="runtime bootstrap manifest",
    )
    if hashlib.sha256(source).hexdigest() != expected_manifest_digest:
        raise RuntimeLockError("runtime bootstrap manifest digest differs")
    try:
        document = json.loads(source, object_pairs_hook=_closed_object)
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeLockError("runtime bootstrap manifest is invalid") from exc
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "python_minor",
        "repository",
        "commit_oid",
        "tree_oid",
        "environment_root",
        "lock_sha256",
        "sentinel_sha256",
        "artifacts",
        "local_project",
    }:
        raise RuntimeLockError("runtime bootstrap manifest is invalid")
    lock_source, _ = _read_bound_regular_file(
        lock_file,
        maximum_bytes=MAX_LOCK_BYTES,
        error_type=RuntimeLockError,
        label="project lock",
    )
    try:
        environment_root = Path(document["environment_root"]).resolve(strict=True)
    except (OSError, TypeError) as exc:
        raise RuntimeLockError("runtime bootstrap manifest is invalid") from exc
    try:
        head = _bound_git_oid("HEAD")
        tree = _bound_git_oid("HEAD^{tree}")
        status = _bound_git_output(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            maximum_bytes=1024 * 1024,
        )
        _assert_default_git_index()
    except (CoverageGateError, UnicodeError) as exc:
        raise RuntimeLockError("runtime repository binding is unavailable") from exc
    if (
        document["schema_version"] != 1
        or document["python_minor"] != f"{sys.version_info.major}.{sys.version_info.minor}"
        or document["repository"] != str(ROOT.resolve(strict=True))
        or environment_root != Path(sys.prefix).resolve(strict=True)
        or document["lock_sha256"] != hashlib.sha256(lock_source).hexdigest()
        or document["sentinel_sha256"] != hashlib.sha256(sentinel.encode("ascii")).hexdigest()
        or re.fullmatch(r"[0-9a-f]{40}", str(document["commit_oid"])) is None
        or re.fullmatch(r"[0-9a-f]{40}", str(document["tree_oid"])) is None
        or document["commit_oid"] != head
        or document["tree_oid"] != tree
        or status != b""
    ):
        raise RuntimeLockError("runtime bootstrap manifest binding differs")
    candidates = _locked_wheels(lock_file)
    artifacts = document["artifacts"]
    local = document["local_project"]
    if not isinstance(artifacts, list) or len(artifacts) != len(locked) or not isinstance(local, dict):
        raise RuntimeLockError("runtime bootstrap artifact set is invalid")
    bound: dict[str, dict[str, object]] = {}
    for row in (*artifacts, local):
        if not isinstance(row, dict) or set(row) != {
            "name", "version", "wheel_path", "sha256", "files", *( {"url"} if row is not local else set())
        }:
            raise RuntimeLockError("runtime bootstrap artifact row is invalid")
        name = row.get("name")
        version = row.get("version")
        digest = row.get("sha256")
        if not isinstance(name, str) or not isinstance(version, str) or not isinstance(digest, str):
            raise RuntimeLockError("runtime bootstrap artifact row is invalid")
        normalized = _normalized_name(name)
        if normalized in bound or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise RuntimeLockError("runtime bootstrap artifact row is invalid")
        if normalized == "hsconfig":
            if version != str(document.get("local_project", {}).get("version")):
                raise RuntimeLockError("runtime bootstrap local artifact differs")
        else:
            if normalized not in locked or locked[normalized][1] != version:
                raise RuntimeLockError("runtime bootstrap artifact differs from project lock")
            url = row.get("url")
            if not isinstance(url, str) or (url, digest) not in candidates[normalized]:
                raise RuntimeLockError("runtime bootstrap artifact differs from project lock")
        wheel_path = Path(str(row.get("wheel_path", "")))
        try:
            wheel_resolved = wheel_path.resolve(strict=True)
            bootstrap_root = manifest_path.parent.resolve(strict=True)
        except OSError as exc:
            raise RuntimeLockError("runtime bootstrap wheel path is invalid") from exc
        if bootstrap_root not in wheel_resolved.parents or ROOT in wheel_resolved.parents:
            raise RuntimeLockError("runtime bootstrap wheel path is invalid")
        wheel_source, _ = _read_bound_regular_file(
            wheel_path,
            maximum_bytes=MAX_RUNTIME_ARTIFACT_BYTES,
            error_type=RuntimeLockError,
            label="runtime bootstrap wheel",
        )
        if hashlib.sha256(wheel_source).hexdigest() != digest or row.get("files") != _wheel_inventory(wheel_source):
            raise RuntimeLockError("runtime bootstrap wheel inventory differs")
        copied = dict(row)
        copied["_wheel_source"] = wheel_source
        if normalized == "hsconfig":
            copied["_commit_oid"] = str(document["commit_oid"])
            copied["_tree_oid"] = str(document["tree_oid"])
        bound[normalized] = copied
    if set(bound) != set(locked) | {"hsconfig"}:
        raise RuntimeLockError("runtime bootstrap artifact set differs")
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
        os.name == "nt"
        and isinstance(artifact_name, str)
        and _normalized_name(artifact_name) == "pip"
        and "pip3" in console_names
    ):
        versioned_launcher = (
            f"pip{sys.version_info.major}.{sys.version_info.minor}.exe"
        )
        result.add(
            os.path.relpath(scripts / versioned_launcher, root).replace("\\", "/")
        )
    return result


def _bound_git_output(
    *arguments: str,
    maximum_bytes: int,
) -> bytes:
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
            ("git", "--no-replace-objects", "-C", str(ROOT), *arguments),
            cwd=ROOT,
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


def _bound_git_oid(revision: str) -> str:
    source = _bound_git_output(
        "rev-parse",
        revision,
        maximum_bytes=64,
    )
    if re.fullmatch(rb"[0-9a-f]{40}\n", source) is None:
        raise RuntimeLockError("local project repository identity is invalid")
    return source[:-1].decode("ascii")


def _assert_default_git_index() -> None:
    source = _bound_git_output(
        "ls-files",
        "-v",
        "-z",
        "--full-name",
        maximum_bytes=64 * 1024 * 1024,
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


def _committed_local_tree(
    artifact: Mapping[str, object] | None,
) -> dict[str, str]:
    _commit_oid, tree_oid = _local_repository_oids(artifact)
    source = _bound_git_output(
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        tree_oid,
        "--",
        "src/hsconfig",
        maximum_bytes=64 * 1024 * 1024,
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
    try:
        head = _bound_git_oid("HEAD")
        head_tree = _bound_git_oid("HEAD^{tree}")
        committed_tree = _bound_git_oid(f"{commit_oid}^{{tree}}")
        status = _bound_git_output(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            maximum_bytes=1024 * 1024,
        )
        _assert_default_git_index()
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
        normalized_version = re.sub(r"[^A-Za-z0-9.]+", "_", artifact_version)
        expected_dist_info = f"pip-{normalized_version}.dist-info"
        expected_direct_url_path = f"{expected_dist_info}/direct_url.json"
        direct_url_source = direct_url.encode("utf-8")
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
        or _normalized_name(artifact_name) != "pip"
        or not isinstance(artifact_version, str)
        or not normalized_version
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
            "url": wheel_path.as_uri(),
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
                    _matches_committed_local_payload(
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


def _assert_runtime_matches_lock(lock_file: Path = LOCK_FILE) -> None:
    locked = _locked_versions(lock_file)
    artifacts = _load_runtime_manifest(lock_file, locked)
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
        distributions = visible[normalized]
        if len(distributions) != 1:
            raise RuntimeLockError("locked package has duplicate visible distributions")
        distribution = distributions[0]
        if str(distribution.version) != expected_version:
            raise RuntimeLockError("installed package version differs from project lock")
        claimed_paths.update(
            _assert_distribution_origin(
                distribution,
                local_project=False,
                artifact=artifacts[normalized] if artifacts is not None else None,
            )
        )
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
    except (UnicodeError, tomllib.TOMLDecodeError, SyntaxError, KeyError, TypeError) as exc:
        raise RuntimeLockError("project metadata version is invalid") from exc
    if not isinstance(project_version, str) or str(local[0].version) != project_version:
        raise RuntimeLockError("local project version differs from repository")
    claimed_paths.update(
        _assert_distribution_origin(
            local[0],
            local_project=True,
            artifact=artifacts["hsconfig"] if artifacts is not None else None,
        )
    )
    if artifacts is not None:
        _assert_runtime_tree_closed(claimed_paths, Path(sys.prefix))


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


def _find_owned_directory(
    temporary_root: Path,
    requested_path: Path,
    expected_identity: tuple[int, int],
) -> Path | None:
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


def _cleanup_owned_run_root(
    temporary_root: Path,
    requested_path: Path,
    expected_identity: tuple[int, int],
) -> None:
    owned = _find_owned_directory(temporary_root, requested_path, expected_identity)
    if owned is None:
        raise CoverageGateError("coverage run directory ownership was lost")
    quarantine = temporary_root / f".hsconfig-coverage-quarantine-{os.getpid()}-{os.urandom(8).hex()}"
    try:
        os.replace(owned, quarantine)
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


def _delete_windows_entry(
    path: Path,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    import ctypes
    from ctypes import wintypes

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
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(
        str(path),
        0x00010000 | 0x00000080 | 0x00000001,
        0x00000001 | 0x00000002,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    if handle in {0, -1, ctypes.c_void_p(-1).value}:
        raise CoverageGateError("coverage quarantine handle cannot be opened")
    delete_marked = False
    try:
        before = path.lstat()
        if expected_identity is not None and (before.st_dev, before.st_ino) != expected_identity:
            raise CoverageGateError("coverage quarantine identity changed")
        if stat.S_ISDIR(before.st_mode) and not stat.S_ISLNK(before.st_mode) and not _is_reparse(before):
            for entry in list(os.scandir(path)):
                child_path = Path(entry.path)
                child_metadata = child_path.lstat()
                _delete_windows_entry(
                    child_path,
                    (child_metadata.st_dev, child_metadata.st_ino),
                )
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
            raise CoverageGateError("coverage quarantine identity changed")
        disposition = wintypes.BOOL(True)
        if not kernel32.SetFileInformationByHandle(
            handle,
            4,
            ctypes.byref(disposition),
            ctypes.sizeof(disposition),
        ):
            raise CoverageGateError("coverage quarantine delete disposition failed")
        delete_marked = True
    except OSError as exc:
        raise CoverageGateError("coverage quarantine cleanup failed") from exc
    finally:
        kernel32.CloseHandle(handle)
    if delete_marked and (path.exists() or path.is_symlink()):
        raise CoverageGateError("coverage quarantine cleanup left residue")


@contextmanager
def isolated_coverage_environment() -> Iterator[CoverageRun]:
    configured_temporary_root = Path(tempfile.gettempdir())
    try:
        temporary_metadata = configured_temporary_root.lstat()
    except OSError as exc:
        raise CoverageGateError("temporary root cannot be inspected") from exc
    if (
        not stat.S_ISDIR(temporary_metadata.st_mode)
        or stat.S_ISLNK(temporary_metadata.st_mode)
        or _is_reparse(temporary_metadata)
    ):
        raise CoverageGateError("temporary root is unsafe")
    temporary_root = configured_temporary_root.resolve()
    if temporary_root == ROOT or ROOT in temporary_root.parents:
        raise CoverageGateError("temporary root must be outside repository")
    run_root: Path | None = None
    run_identity: tuple[int, int] | None = None
    try:
        run_root = Path(
            tempfile.mkdtemp(prefix="hsconfig-coverage-run-", dir=temporary_root)
        ).resolve()
        created_metadata = run_root.lstat()
        run_identity = (created_metadata.st_dev, created_metadata.st_ino)
        if _coverage_directory_identity(run_root) != run_identity:
            raise CoverageGateError("coverage run directory changed during setup")
        environment = os.environ.copy()
        for key in tuple(environment):
            if key.upper() in {
                "PYTEST_ADDOPTS",
                "PYTHONHOME",
                "PYTHONPATH",
                "PYTHONUSERBASE",
                "PYTEST_DEBUG_TEMPROOT",
                "HYPOTHESIS_STORAGE_DIRECTORY",
            }:
                environment.pop(key, None)
        coverage_data = run_root / ".coverage"
        coverage_json = run_root / "coverage.json"
        pytest_temp = run_root / "pytest-temp"
        hypothesis_storage = run_root / "hypothesis"
        pytest_temp.mkdir()
        hypothesis_storage.mkdir()
        environment.update(
            {
                "COVERAGE_FILE": str(coverage_data),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
                "PYTEST_PLUGINS": "pytest_cov.plugin,_hypothesis_pytestplugin",
                "PYTEST_DEBUG_TEMPROOT": str(pytest_temp),
                "HYPOTHESIS_STORAGE_DIRECTORY": str(hypothesis_storage),
            }
        )
        yield CoverageRun(
            run_root=run_root,
            run_identity=run_identity,
            coverage_data=coverage_data,
            coverage_json=coverage_json,
            environment=environment,
        )
    finally:
        if run_root is not None and run_identity is not None:
            _cleanup_owned_run_root(temporary_root, run_root, run_identity)


def _pytest_coverage_command(coverage_json: Path) -> tuple[str, ...]:
    return (
        sys.executable,
        "-m",
        "pytest",
        "--cov=src/hsconfig",
        "--cov-branch",
        "--cov-config=pyproject.toml",
        "--cov-fail-under=90",
        f"--cov-report=json:{coverage_json}",
        "--cov-report=term-missing",
        "-p",
        "no:cacheprovider",
    )


def _checker_command() -> tuple[str, ...]:
    return (sys.executable, "-c", CHECKER_BRIDGE)


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
) -> _BoundedResult:
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
            (sys.executable, "-c", _GATED_LAUNCHER),
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
) -> subprocess.CompletedProcess[str]:
    bounded = _run_bounded_process(
        command,
        cwd=cwd,
        env=env,
        timeout=timeout,
        stdin_data=input_bytes,
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
) -> subprocess.CompletedProcess[str]:
    bounded = _run_bounded_process(
        command,
        cwd=cwd,
        env=env,
        timeout=PYTEST_TIMEOUT_SECONDS,
    )
    _diagnostic_digest("pytest stdout", bounded.stdout)
    _diagnostic_digest("pytest stderr", bounded.stderr)
    transport_failed = (
        bounded.stdout.error is not None or bounded.stderr.error is not None
    )
    return subprocess.CompletedProcess(
        command,
        2 if bounded.timed_out or transport_failed else bounded.completed.returncode,
        stdout="",
        stderr="",
    )


def main() -> int:
    try:
        _assert_runtime_matches_lock(LOCK_FILE)
        pytest_failure: int | None = None
        checker_result: subprocess.CompletedProcess[str] | None = None
        with isolated_coverage_environment() as run:
            pytest_result = _run_pytest_bounded(
                _pytest_coverage_command(run.coverage_json),
                cwd=ROOT,
                env=run.environment,
            )
            if pytest_result.returncode != 0:
                pytest_failure = _portable_child_returncode(pytest_result.returncode)
            else:
                identity = _coverage_report_identity(
                    run.run_root,
                    run.coverage_json,
                    run.run_identity,
                )
                checker_result = _run_checker_bounded(
                    _checker_command(),
                    cwd=ROOT,
                    env=run.environment,
                    timeout=CHECKER_TIMEOUT_SECONDS,
                    input_bytes=identity.content,
                )
                _assert_coverage_report_unchanged(
                    run.run_root,
                    run.coverage_json,
                    identity,
                    run.run_identity,
                )
        if pytest_failure is not None:
            _emit_failure("pytest coverage execution failed", pytest_failure)
            return pytest_failure
        if checker_result is None:
            raise CoverageGateError("coverage checker did not run")
        return _forward_checker_result(checker_result)
    except RuntimeLockError:
        print("coverage gate runtime lock mismatch", file=sys.stderr)
        _emit_failure("coverage runtime does not match project lock", 2)
        return 2
    except CoverageGateError:
        print("coverage gate validation failure", file=sys.stderr)
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
    if len(sys.argv) != 1:
        _emit_failure("usage: run_coverage_gate.py", 2)
        raise SystemExit(2)
    raise SystemExit(main())
