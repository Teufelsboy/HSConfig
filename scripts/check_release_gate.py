from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import tomllib
from typing import Any, Mapping, NamedTuple, Sequence
from urllib.request import Request, urlopen
import uuid
import venv
import zipfile

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - Windows has the native handle lease below.
    _fcntl = None
try:
    import msvcrt as _msvcrt
except ImportError:  # pragma: no cover - POSIX has the descriptor lease below.
    _msvcrt = None


# The documented parent remains stdlib-only and must not create checkout
# bytecode before the child has run repository hygiene.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
_SENTINEL = "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL"
_MANIFEST = "HSCONFIG_RUNTIME_MANIFEST"
_MANIFEST_DIGEST = "HSCONFIG_RUNTIME_MANIFEST_SHA256"
_MAX_BOOTSTRAP_FILE = 512 * 1024 * 1024
_MAX_CONTROLLER_SOURCE = 4 * 1024 * 1024
_MAX_CHILD_STDOUT = 1024 * 1024
_BOOTSTRAP_CHILD_TIMEOUT_SECONDS = 21_600
_SUPPORTED_PYTHON_MINORS = {"3.11", "3.12"}
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_GATED_CHILD_LAUNCHER = (
    "import json,os,subprocess,sys; header=bytearray(); "
    "[(header.extend(chunk),None)[1] for chunk in iter(lambda:os.read(0,1),b'\\n')]; "
    "argv=json.loads(header); "
    "assert isinstance(argv,list) and argv and all(isinstance(x,str) for x in argv); "
    "raise SystemExit(subprocess.run(argv,stdin=sys.stdin.buffer).returncode)"
)
_VERIFIED_CONTROLLER_LAUNCHER = (
    "import sys; path=sys.argv.pop(1); sys.argv[0]=path; "
    "line=sys.stdin.buffer.readline(32); "
    "(line.endswith(b'\\n') and line[:-1].isdigit()) or sys.exit(2); size=int(line); "
    f"(0<size<={_MAX_CONTROLLER_SOURCE}) or sys.exit(2); "
    "source=sys.stdin.buffer.read(size); (len(source)==size) or sys.exit(2); "
    "scope={'__name__':'__main__','__file__':path,'__package__':None,'__cached__':None}; "
    "exec(compile(source,path,'exec'),scope,scope)"
)
_GIT_BLOB_BATCH_LAUNCHER = (
    "import json,subprocess,sys; line=sys.stdin.buffer.readline(65537); "
    "(line.endswith(b'\\n') and len(line)<=65536) or sys.exit(2); "
    "argv=json.loads(line); "
    "(isinstance(argv,list) and 1<=len(argv)<=32 and "
    "all(isinstance(value,str) and value for value in argv)) or sys.exit(2); "
    "payload=sys.stdin.buffer.read(410001); len(payload)<=410000 or sys.exit(2); "
    "raise SystemExit(subprocess.run(argv,input=payload,shell=False).returncode)"
)


class _CliError(ValueError):
    pass


class _BootstrapError(RuntimeError):
    pass


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


def _process_tree_gate_interpreter(fallback: str | Path) -> str:
    if os.name != "nt":
        return str(fallback)
    raw_base = getattr(sys, "_base_executable", None)
    if not isinstance(raw_base, str) or not raw_base:
        raise _BootstrapError("process gate interpreter is invalid")
    candidate = Path(raw_base)
    if not candidate.is_absolute():
        raise _BootstrapError("process gate interpreter is invalid")
    try:
        metadata = candidate.lstat()
        canonical = candidate.resolve(strict=True)
        canonical_metadata = canonical.lstat()
    except (OSError, RuntimeError) as exc:
        raise _BootstrapError("process gate interpreter is invalid") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(canonical_metadata.st_mode)
        or _is_reparse(canonical_metadata)
        or not stat.S_ISREG(canonical_metadata.st_mode)
    ):
        raise _BootstrapError("process gate interpreter is invalid")
    return str(canonical)


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _CliError(f"argument_error:{message}")


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description="Run the canonical local release gate.")
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--outputs", required=True, type=Path)
    parser.add_argument("--owner-repo", type=Path)
    parser.add_argument(
        "--tree-mode",
        choices=("working-pre-cutover", "candidate", "final"),
        default="final",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--internal-check",
        choices=("publishable_path_scan", "repository_hygiene"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--locked-check",
        choices=(
            "ci-source-baseline",
            "ci-source-revalidate",
            "ci-wheelhouse-audit",
            "full-tests-and-coverage",
        ),
        help=argparse.SUPPRESS,
    )
    return parser


def _closed_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_bound(path: Path, maximum: int = _MAX_BOOTSTRAP_FILE) -> bytes:
    try:
        parent_before = path.parent.lstat()
        before = path.lstat()
        if (
            not stat.S_ISDIR(parent_before.st_mode)
            or stat.S_ISLNK(parent_before.st_mode)
            or _is_reparse(parent_before)
            or not stat.S_ISREG(before.st_mode)
            or stat.S_ISLNK(before.st_mode)
            or _is_reparse(before)
            or getattr(before, "st_nlink", 1) not in {0, 1}
            or before.st_size > maximum
        ):
            raise _BootstrapError("bootstrap input is unsafe")
        descriptor = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                raise _BootstrapError("bootstrap input changed")
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(1024 * 1024, maximum - total + 1))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > maximum:
                    raise _BootstrapError("bootstrap input exceeds size limit")
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        path_after = path.lstat()
        parent_after = path.parent.lstat()
    except _BootstrapError:
        raise
    except OSError as exc:
        raise _BootstrapError("bootstrap input cannot be read") from exc
    def identity(row: os.stat_result) -> tuple[int, int, int, int, int, int]:
        return (
            row.st_dev,
            row.st_ino,
            row.st_size,
            row.st_mtime_ns,
            row.st_ctime_ns,
            row.st_mode,
        )
    if (
        identity(opened) != identity(after)
        or identity(before) != identity(path_after)
        or identity(parent_before) != identity(parent_after)
        or total != opened.st_size
    ):
        raise _BootstrapError("bootstrap input changed")
    return b"".join(chunks)


def _bootstrap_lock_binding_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    identity_time_ns = metadata.st_ctime_ns
    if os.name == "nt":
        birthtime_ns = getattr(metadata, "st_birthtime_ns", None)
        if birthtime_ns is not None:
            identity_time_ns = int(birthtime_ns)
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        identity_time_ns,
        metadata.st_mode,
    )


def _bootstrap_lock_binding(
    path: Path,
    expected_source: bytes,
) -> tuple[int, int, int, int, int, int, str]:
    source = _read_bound(path, 8 * 1024 * 1024)
    if source != expected_source:
        raise _BootstrapError("bootstrap lock content changed")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise _BootstrapError("bootstrap lock identity cannot be read") from exc
    return (
        *_bootstrap_lock_binding_identity(metadata),
        hashlib.sha256(source).hexdigest(),
    )


def _verify_bootstrap_lock_binding(
    path: Path,
    expected_source: bytes,
    expected_binding: tuple[int, int, int, int, int, int, str],
) -> None:
    if _bootstrap_lock_binding(path, expected_source) != expected_binding:
        raise _BootstrapError("bootstrap lock identity changed")


def _materialize_bootstrap_lock(
    bootstrap_root: Path,
    source: bytes,
) -> tuple[Path, tuple[int, int, int, int, int, int, str]]:
    path = bootstrap_root / "pylock.toml"
    try:
        with path.open("xb") as handle:
            handle.write(source)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise _BootstrapError("canonical bootstrap lock cannot be materialized") from exc
    return path, _bootstrap_lock_binding(path, source)


def _windows_open_bound_descriptor(path: Path, *, directory: bool) -> int:
    if _msvcrt is None:
        raise _BootstrapError("bootstrap lock lease is unavailable")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    )
    create_file.restype = wintypes.HANDLE
    handle = create_file(
        str(path),
        0x00000080 if directory else 0x80000000,  # FILE_READ_ATTRIBUTES / GENERIC_READ
        0x00000003 if directory else 0x00000001,  # deny delete; file also denies write
        None,
        3,  # OPEN_EXISTING
        (0x02000000 if directory else 0x08000000) | 0x00200000,
        None,
    )
    if handle in {None, ctypes.c_void_p(-1).value}:
        raise _BootstrapError("bootstrap lock lease cannot be acquired")
    try:
        return _msvcrt.open_osfhandle(
            int(handle),
            os.O_RDONLY | getattr(os, "O_BINARY", 0),
        )
    except BaseException:
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        close_handle(handle)
        raise


def _windows_descriptor_path(descriptor: int) -> str:
    if _msvcrt is None:
        raise _BootstrapError("bootstrap lock lease is unavailable")
    handle = _msvcrt.get_osfhandle(descriptor)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_path = kernel32.GetFinalPathNameByHandleW
    get_path.argtypes = (
        wintypes.HANDLE,
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    )
    get_path.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32_768)
    length = get_path(handle, buffer, len(buffer), 0)
    if not length or length >= len(buffer):
        raise _BootstrapError("bootstrap lock lease path cannot be read")
    value = buffer.value
    if value.startswith("\\\\?\\UNC\\"):
        value = "\\\\" + value[8:]
    elif value.startswith("\\\\?\\"):
        value = value[4:]
    return os.path.normcase(os.path.abspath(value))


def _verify_windows_lock_lease(
    path: Path,
    expected_source: bytes,
    expected_binding: tuple[int, int, int, int, int, int, str],
    parent_descriptor: int,
    file_descriptor: int,
    parent_identity: tuple[int, int, int, int, int, int],
    file_identity: tuple[int, int, int, int, int, int],
) -> None:
    try:
        parent_metadata = os.fstat(parent_descriptor)
        file_metadata = os.fstat(file_descriptor)
    except OSError as exc:
        raise _BootstrapError("bootstrap lock lease identity cannot be read") from exc
    current_parent = _descriptor_stat_identity(parent_metadata)
    current_file = _descriptor_stat_identity(file_metadata)
    if (
        current_parent != parent_identity
        or current_file != file_identity
        or not stat.S_ISDIR(parent_metadata.st_mode)
        or _is_reparse(parent_metadata)
        or not stat.S_ISREG(file_metadata.st_mode)
        or _is_reparse(file_metadata)
        or getattr(file_metadata, "st_nlink", 1) not in {0, 1}
        or _windows_descriptor_path(parent_descriptor)
        != os.path.normcase(os.path.abspath(path.parent.resolve(strict=True)))
        or _windows_descriptor_path(file_descriptor)
        != os.path.normcase(os.path.abspath(path.resolve(strict=True)))
    ):
        raise _BootstrapError("bootstrap lock lease identity changed")
    source = _descriptor_source(file_descriptor)
    if (
        source != expected_source
        or hashlib.sha256(source).hexdigest() != expected_binding[-1]
    ):
        raise _BootstrapError("bootstrap lock lease content changed")
    _verify_bootstrap_lock_binding(path, expected_source, expected_binding)


def _descriptor_stat_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        metadata.st_mode,
    )


def _descriptor_source(descriptor: int, maximum: int = 8 * 1024 * 1024) -> bytes:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise _BootstrapError("bootstrap lock exceeds size limit")
    except _BootstrapError:
        raise
    except OSError as exc:
        raise _BootstrapError("bootstrap lock lease cannot be read") from exc
    return b"".join(chunks)


def _verify_posix_lock_lease(
    path: Path,
    expected_source: bytes,
    expected_binding: tuple[int, int, int, int, int, int, str],
    parent_descriptor: int,
    file_descriptor: int,
    parent_identity: tuple[int, int, int, int, int, int],
    file_identity: tuple[int, int, int, int, int, int],
) -> None:
    try:
        current_parent = _descriptor_stat_identity(os.fstat(parent_descriptor))
        current_file = _descriptor_stat_identity(os.fstat(file_descriptor))
    except OSError as exc:
        raise _BootstrapError("bootstrap lock lease identity cannot be read") from exc
    if current_parent != parent_identity or current_file != file_identity:
        raise _BootstrapError("bootstrap lock lease identity changed")
    source = _descriptor_source(file_descriptor)
    if (
        source != expected_source
        or hashlib.sha256(source).hexdigest() != expected_binding[-1]
    ):
        raise _BootstrapError("bootstrap lock lease content changed")
    _verify_bootstrap_lock_binding(path, expected_source, expected_binding)


@contextmanager
def _bootstrap_lock_execution_lease(
    path: Path,
    expected_source: bytes,
    expected_binding: tuple[int, int, int, int, int, int, str],
):
    if os.name == "nt":
        parent_descriptor = _windows_open_bound_descriptor(path.parent, directory=True)
        try:
            file_descriptor = _windows_open_bound_descriptor(path, directory=False)
        except BaseException:
            os.close(parent_descriptor)
            raise
        try:
            parent_metadata = os.fstat(parent_descriptor)
            file_metadata = os.fstat(file_descriptor)
            parent_identity = _descriptor_stat_identity(parent_metadata)
            file_identity = _descriptor_stat_identity(file_metadata)
            file_binding_identity = _bootstrap_lock_binding_identity(file_metadata)
            if (
                not stat.S_ISDIR(parent_metadata.st_mode)
                or _is_reparse(parent_metadata)
                or not stat.S_ISREG(file_metadata.st_mode)
                or _is_reparse(file_metadata)
                or file_binding_identity != expected_binding[:6]
            ):
                raise _BootstrapError("bootstrap lock lease identity changed")

            def verify() -> None:
                _verify_windows_lock_lease(
                    path,
                    expected_source,
                    expected_binding,
                    parent_descriptor,
                    file_descriptor,
                    parent_identity,
                    file_identity,
                )
            verify()
            try:
                yield
            except BaseException:
                try:
                    verify()
                except BaseException:
                    pass
                raise
            else:
                verify()
        finally:
            try:
                os.close(file_descriptor)
            finally:
                os.close(parent_descriptor)
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_descriptor = os.open(path.parent, flags)
        try:
            file_descriptor = os.open(
                path.name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
        except BaseException:
            os.close(parent_descriptor)
            raise
    except OSError as exc:
        raise _BootstrapError("bootstrap lock lease cannot be acquired") from exc
    try:
        if _fcntl is None:
            raise _BootstrapError("bootstrap lock lease is unavailable")
        _fcntl.flock(parent_descriptor, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        _fcntl.flock(file_descriptor, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        parent_identity = _descriptor_stat_identity(os.fstat(parent_descriptor))
        file_identity = _descriptor_stat_identity(os.fstat(file_descriptor))
        if (
            not stat.S_ISDIR(parent_identity[-1])
            or not stat.S_ISREG(file_identity[-1])
            or file_identity != expected_binding[:6]
        ):
            raise _BootstrapError("bootstrap lock lease identity changed")

        def verify() -> None:
            _verify_posix_lock_lease(
                path,
                expected_source,
                expected_binding,
                parent_descriptor,
                file_descriptor,
                parent_identity,
                file_identity,
            )
        verify()
        try:
            yield
        except BaseException:
            try:
                verify()
            except BaseException:
                pass
            raise
        else:
            verify()
    except OSError as exc:
        raise _BootstrapError("bootstrap lock lease cannot be acquired") from exc
    finally:
        try:
            os.close(file_descriptor)
        finally:
            os.close(parent_descriptor)


def _project_version(repository: Path) -> str:
    try:
        tree = ast.parse(_read_bound(repository / "src" / "hsconfig" / "version.py"))
    except (SyntaxError, UnicodeError) as exc:
        raise _BootstrapError("project version cannot be read") from exc
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
        raise _BootstrapError("project version is invalid")
    return values[0]


def _failure(version: str, message: str) -> dict[str, Any]:
    safe_message = (
        message
        if message
        in {
            "release gate child stdout read failed",
            "release gate child stdout exceeded size limit",
            "release gate child timed out",
        }
        else "release gate bootstrap failed"
    )
    return {
        "passed": False,
        "final_release_ready": False,
        "version": version,
        "commit_oid": "",
        "checks": [],
        "errors": [safe_message],
        "diagnostic_id": hashlib.sha256(message.encode("utf-8")).hexdigest()[:16],
    }


def _emit(document: Mapping[str, Any]) -> None:
    print(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    )


def _base_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        upper = key.upper()
        if (
            upper.startswith(("GIT_", "PIP_", "PYTHON", "PYTEST_", "HYPOTHESIS_"))
            or upper in {"VIRTUAL_ENV", "CONDA_PREFIX", _SENTINEL, _MANIFEST, _MANIFEST_DIGEST}
        ):
            environment.pop(key, None)
    environment.update(
        {
            "PIP_CONFIG_FILE": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def _run(command: tuple[str, ...], *, cwd: Path, env: Mapping[str, str]) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=dict(env),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        timeout=1_800,
    )
    if completed.returncode != 0:
        raise _BootstrapError("bootstrap subprocess failed")


def _git(repository: Path, *arguments: str) -> str:
    environment = _base_environment()
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        shell=False,
        timeout=120,
    )
    if completed.returncode != 0:
        raise _BootstrapError("repository bootstrap binding failed")
    return completed.stdout.strip()


def _selected_lock(repository: Path) -> tuple[Path, dict[str, Any], bytes]:
    minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    if minor not in _SUPPORTED_PYTHON_MINORS:
        raise _BootstrapError("canonical release gate supports Python 3.11 or 3.12")
    path = repository / f"pylock.{minor}.toml"
    source = _read_bound(path, 8 * 1024 * 1024)
    try:
        document = tomllib.loads(source.decode("utf-8"))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise _BootstrapError("selected bootstrap lock is invalid") from exc
    packages = document.get("packages")
    if not isinstance(packages, list) or len(packages) != 43:
        raise _BootstrapError("selected bootstrap lock must contain exactly 43 packages")
    return path, document, source


def _lock_rows(document: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for package in document["packages"]:
        if not isinstance(package, dict):
            raise _BootstrapError("selected bootstrap package is invalid")
        name = package.get("name")
        version = package.get("version")
        wheels = package.get("wheels")
        if not isinstance(name, str) or not isinstance(version, str) or not isinstance(wheels, list):
            raise _BootstrapError("selected bootstrap package is invalid")
        key = (re.sub(r"[-_.]+", "-", name).casefold(), version)
        if key in rows:
            raise _BootstrapError("selected bootstrap lock contains duplicate package")
        candidates: list[dict[str, str]] = []
        for wheel in wheels:
            hashes = wheel.get("hashes") if isinstance(wheel, dict) else None
            if (
                not isinstance(wheel, dict)
                or not isinstance(wheel.get("name"), str)
                or not isinstance(wheel.get("url"), str)
                or not isinstance(hashes, dict)
                or re.fullmatch(r"[0-9a-f]{64}", str(hashes.get("sha256"))) is None
            ):
                raise _BootstrapError("selected bootstrap wheel is invalid")
            candidates.append(
                {
                    "name": wheel["name"],
                    "url": wheel["url"],
                    "sha256": hashes["sha256"],
                }
            )
        if not candidates:
            raise _BootstrapError("selected bootstrap wheel set is empty")
        rows[key] = {"name": name, "version": version, "wheels": candidates}
    return rows


def _download(url: str, destination: Path, sha256: str) -> None:
    request = Request(url, headers={"User-Agent": "hsconfig-release-gate/1"})
    digest = hashlib.sha256()
    size = 0
    temporary = destination.with_name(destination.name + ".partial")
    try:
        with urlopen(request, timeout=120) as response, temporary.open("xb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_BOOTSTRAP_FILE:
                    raise _BootstrapError("bootstrap artifact exceeds size limit")
                digest.update(chunk)
                handle.write(chunk)
        if digest.hexdigest() != sha256:
            raise _BootstrapError("bootstrap artifact hash mismatch")
        os.replace(temporary, destination)
    except BaseException:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _venv_python(environment_root: Path) -> Path:
    return environment_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _bootstrap_pip(
    python: Path,
    lock_rows: Mapping[tuple[str, str], Mapping[str, Any]],
    root: Path,
    environment: Mapping[str, str],
) -> dict[str, object]:
    pip_rows = [row for (name, _version), row in lock_rows.items() if name == "pip"]
    if len(pip_rows) != 1:
        raise _BootstrapError("selected bootstrap lock has no unique pip")
    compatible = [
        wheel
        for wheel in pip_rows[0]["wheels"]
        if wheel["name"].endswith("-py3-none-any.whl")
    ]
    if len(compatible) != 1:
        raise _BootstrapError("selected bootstrap pip wheel is ambiguous")
    wheel = compatible[0]
    destination = root / wheel["name"]
    _download(wheel["url"], destination, wheel["sha256"])
    files = _wheel_inventory(destination)
    pip_environment = dict(environment)
    pip_environment["PYTHONPATH"] = str(destination)
    _run(
        (
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--force-reinstall",
            str(destination),
        ),
        cwd=root,
        env=pip_environment,
    )
    return {
        "name": pip_rows[0]["name"],
        "version": pip_rows[0]["version"],
        "url": wheel["url"],
        "sha256": wheel["sha256"],
        "wheel_path": str(destination),
        "files": files,
    }


def _safe_extract_archive(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:") as bundle:
        members = bundle.getmembers()
        if len(members) > 10_000:
            raise _BootstrapError("committed source archive is oversized")
        for member in members:
            pure = PurePosixPath(member.name)
            if (
                pure.is_absolute()
                or any(part in {"", ".", ".."} for part in pure.parts)
                or not (member.isfile() or member.isdir())
                or member.size > _MAX_BOOTSTRAP_FILE
                or (
                    member.isfile()
                    and member.mode not in {0o644, 0o664, 0o755, 0o775}
                )
            ):
                raise _BootstrapError("committed source archive is unsafe")
            target = destination.joinpath(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = bundle.extractfile(member)
                if stream is None:
                    raise _BootstrapError("committed source archive member is unreadable")
                with target.open("xb") as handle:
                    shutil.copyfileobj(stream, handle, 1024 * 1024)
                os.chmod(target, 0o755 if member.mode & 0o111 else 0o644)


def _assert_repository_identity(repository: Path, commit_oid: str, tree_oid: str) -> None:
    if (
        _git(repository, "rev-parse", "HEAD") != commit_oid
        or _git(repository, "rev-parse", "HEAD^{tree}") != tree_oid
        or _git(repository, "rev-parse", f"{commit_oid}^{{tree}}") != tree_oid
        or _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    ):
        raise _BootstrapError("repository changed during committed source bootstrap")


def _assert_regular_git_tree(
    repository: Path, commit_oid: str
) -> tuple[dict[str, str], ...]:
    listing = _git(repository, "ls-tree", "-rz", "--full-tree", commit_oid)
    records = listing.split("\0")
    if not records or records[-1] != "":
        raise _BootstrapError("committed source tree listing is malformed")
    entries: list[dict[str, str]] = []
    paths: set[str] = set()
    for record in records[:-1]:
        header, separator, name = record.partition("\t")
        fields = header.split()
        if (
            not separator
            or not name
            or len(fields) != 3
            or fields[0] not in {"100644", "100755"}
            or fields[1] != "blob"
            or re.fullmatch(r"[0-9a-f]{40}", fields[2]) is None
            or name in paths
        ):
            raise _BootstrapError("committed source tree contains a non-regular entry")
        pure = PurePosixPath(name)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise _BootstrapError("committed source tree contains an unsafe path")
        paths.add(name)
        entries.append(
            {"path": name, "git_mode": fields[0], "blob_oid": fields[2]}
        )
    if len(entries) > 10_000:
        raise _BootstrapError("committed source tree contains too many entries")
    return tuple(sorted(entries, key=lambda entry: entry["path"]))


def _git_blob_command(repository: Path, argument: str) -> tuple[str, ...]:
    return ("git", "-C", str(repository), "cat-file", argument)


def _run_git_blob_batch(
    repository: Path,
    argument: str,
    requests: bytes,
    *,
    maximum: int,
    timeout: float = 120,
) -> bytes:
    if maximum < 0 or timeout <= 0 or len(requests) > 10_000 * 41:
        raise _BootstrapError("committed source blob batch is invalid")
    target_command = _git_blob_command(repository, argument)
    launch_header = json.dumps(
        list(target_command),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    if len(launch_header) > 65_536:
        raise _BootstrapError("committed source blob batch is invalid")
    launch_input = launch_header + requests
    platform_options: dict[str, object] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process: subprocess.Popen[bytes] | None = None
    lease: _BootstrapProcessTreeLease | None = None
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
        lease = _BootstrapProcessTreeLease(process, baseline)
        if process.stdin is None or process.stdout is None or process.stderr is None:
            raise OSError("committed source blob batch pipes are unavailable")
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
        raise _BootstrapError("committed source blob batch is invalid") from exc
    finally:
        if process is not None:
            if lease is not None:
                lease.terminate_remaining()
            else:
                _terminate_unleased_process(process)
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
        raise _BootstrapError("committed source blob batch transport did not terminate")
    if stdout_oversized.is_set():
        raise _BootstrapError("committed source blob batch stdout exceeded size limit")
    if stderr_oversized.is_set():
        raise _BootstrapError("committed source blob batch stderr exceeded size limit")
    if timed_out:
        raise _BootstrapError("committed source blob batch timed out")
    if transport_errors:
        raise _BootstrapError("committed source blob batch transport is invalid")
    if returncode != 0:
        raise _BootstrapError("committed source blob batch exited nonzero")
    if len(stdout) > maximum or len(stderr) > 64 * 1024:
        raise _BootstrapError("committed source blob batch is invalid")
    return bytes(stdout)


def _git_blob_payloads(
    repository: Path,
    git_entries: Sequence[Mapping[str, str]],
) -> dict[str, bytes]:
    if len(git_entries) > 10_000:
        raise _BootstrapError("committed source blob batch is invalid")
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
            raise _BootstrapError("committed source blob batch is invalid")
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
        raise _BootstrapError("committed source blob batch is invalid")
    sizes: dict[str, int] = {}
    for oid, line in zip(object_oids, lines[:-1], strict=True):
        try:
            fields = line.decode("ascii").split(" ")
        except UnicodeError as exc:
            raise _BootstrapError("committed source blob batch is invalid") from exc
        if (
            len(fields) != 3
            or fields[0] != oid
            or fields[1] != "blob"
            or re.fullmatch(r"0|[1-9][0-9]*", fields[2]) is None
            or line != f"{oid} blob {fields[2]}".encode("ascii")
        ):
            raise _BootstrapError("committed source blob batch is invalid")
        size = int(fields[2])
        if size > _MAX_BOOTSTRAP_FILE:
            raise _BootstrapError("committed source blob batch is invalid")
        sizes[oid] = size
    total_size = sum(sizes[str(entry["blob_oid"])] for entry in git_entries)
    if total_size > _MAX_BOOTSTRAP_FILE:
        raise _BootstrapError("committed source blob batch is invalid")
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
            raise _BootstrapError("committed source blob batch is invalid")
        offset += len(header)
        end = offset + size
        if end >= len(batch) or batch[end : end + 1] != b"\n":
            raise _BootstrapError("committed source blob batch is invalid")
        payload = batch[offset:end]
        digest = hashlib.sha1(
            b"blob " + str(size).encode("ascii") + b"\0" + payload,
            usedforsecurity=False,
        ).hexdigest()
        if digest != oid:
            raise _BootstrapError("committed source blob batch is invalid")
        blobs[oid] = payload
        offset = end + 1
    if offset != len(batch):
        raise _BootstrapError("committed source blob batch is invalid")
    return {
        str(entry["path"]): blobs[str(entry["blob_oid"])]
        for entry in git_entries
    }


def _source_inventory_digest(inventory: object) -> str:
    encoded = json.dumps(
        inventory,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _build_source_inventory(
    source_root: Path,
    git_entries: Sequence[Mapping[str, str]],
) -> tuple[tuple[dict[str, str], ...], str]:
    source_root = source_root.absolute()
    root_metadata = source_root.lstat()
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or _is_reparse(root_metadata)
        or source_root.resolve(strict=True) != source_root
    ):
        raise _BootstrapError("materialized source inventory is unsafe")
    expected = {entry["path"]: entry["git_mode"] for entry in git_entries}
    if len(expected) != len(git_entries):
        raise _BootstrapError("materialized source inventory contains duplicate paths")
    observed_paths: set[str] = set()
    for path in source_root.rglob("*"):
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
            raise _BootstrapError("materialized source inventory is unsafe")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
        ):
            raise _BootstrapError("materialized source inventory is unsafe")
        relative = path.relative_to(source_root).as_posix()
        if relative in observed_paths:
            raise _BootstrapError("materialized source inventory contains duplicate paths")
        observed_paths.add(relative)
    if observed_paths != set(expected):
        raise _BootstrapError("materialized source inventory path set changed")
    rows: list[dict[str, str]] = []
    for relative, git_mode in sorted(expected.items()):
        pure = PurePosixPath(relative)
        if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
            raise _BootstrapError("materialized source inventory is unsafe")
        path = source_root
        for index, part in enumerate(pure.parts):
            path /= part
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise _BootstrapError("materialized source inventory is unsafe")
            final = index == len(pure.parts) - 1
            if (final and not stat.S_ISREG(metadata.st_mode)) or (
                not final and not stat.S_ISDIR(metadata.st_mode)
            ):
                raise _BootstrapError("materialized source inventory is unsafe")
        if source_root not in path.resolve(strict=True).parents:
            raise _BootstrapError("materialized source inventory is unsafe")
        metadata = path.lstat()
        expected_mode = 0o755 if git_mode == "100755" else 0o644
        if os.name != "nt" and stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise _BootstrapError("materialized source inventory mode changed")
        rows.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(_read_bound(path)).hexdigest(),
                "git_mode": git_mode,
            }
        )
    inventory = tuple(rows)
    return inventory, _source_inventory_digest(inventory)


class _SourceBinding(NamedTuple):
    source_root: Path
    commit_oid: str
    tree_oid: str
    inventory: tuple[dict[str, str], ...]
    inventory_sha256: str


class _RuntimeBootstrapBinding(NamedTuple):
    python: Path
    manifest_path: Path
    manifest_sha256: str
    sentinel: str


def _assert_source_inventory(binding: _SourceBinding) -> None:
    if _source_inventory_digest(binding.inventory) != binding.inventory_sha256:
        raise _BootstrapError("materialized source inventory digest changed")
    inventory, digest = _build_source_inventory(
        binding.source_root,
        tuple(
            {"path": row["path"], "git_mode": row["git_mode"]}
            for row in binding.inventory
        ),
    )
    if inventory != binding.inventory or digest != binding.inventory_sha256:
        raise _BootstrapError("materialized source inventory changed")


def _bound_committed_controller(
    manifest_path: Path,
    manifest: object,
) -> tuple[Path, Path, bytes]:
    if not isinstance(manifest, dict):
        raise _BootstrapError("committed source controller binding is invalid")
    manifest_root = manifest_path.parent.resolve(strict=True)
    source_candidate = manifest_root / "committed-source"
    source_metadata = source_candidate.lstat()
    if (
        not stat.S_ISDIR(source_metadata.st_mode)
        or stat.S_ISLNK(source_metadata.st_mode)
        or _is_reparse(source_metadata)
    ):
        raise _BootstrapError("committed source controller binding is invalid")
    source_root = source_candidate.resolve(strict=True)
    if source_root != source_candidate:
        raise _BootstrapError("committed source controller binding is invalid")
    raw_inventory = manifest.get("source_inventory")
    inventory_sha256 = manifest.get("source_inventory_sha256")
    if (
        not isinstance(raw_inventory, list)
        or re.fullmatch(r"[0-9a-f]{64}", str(inventory_sha256)) is None
    ):
        raise _BootstrapError("committed source controller binding is invalid")
    inventory: list[dict[str, str]] = []
    for row in raw_inventory:
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "sha256", "git_mode"}
            or not isinstance(row["path"], str)
            or row["git_mode"] not in {"100644", "100755"}
            or re.fullmatch(r"[0-9a-f]{64}", str(row["sha256"])) is None
        ):
            raise _BootstrapError("committed source controller binding is invalid")
        inventory.append(dict(row))
    if (
        inventory != sorted(inventory, key=lambda row: row["path"])
        or len({row["path"] for row in inventory}) != len(inventory)
    ):
        raise _BootstrapError("committed source controller binding is invalid")
    binding = _SourceBinding(
        source_root=source_root,
        commit_oid=str(manifest.get("commit_oid", "")),
        tree_oid=str(manifest.get("tree_oid", "")),
        inventory=tuple(inventory),
        inventory_sha256=str(inventory_sha256),
    )
    _assert_source_inventory(binding)
    controller_rows = [
        row for row in inventory if row["path"] == "scripts/check_release_gate.py"
    ]
    if len(controller_rows) != 1 or controller_rows[0]["git_mode"] != "100644":
        raise _BootstrapError("committed source controller binding is invalid")
    controller_candidate = source_root / "scripts" / "check_release_gate.py"
    controller_metadata = controller_candidate.lstat()
    controller_path = controller_candidate.resolve(strict=True)
    controller_source = _read_bound(controller_path, _MAX_CONTROLLER_SOURCE)
    if (
        not stat.S_ISREG(controller_metadata.st_mode)
        or stat.S_ISLNK(controller_metadata.st_mode)
        or _is_reparse(controller_metadata)
        or controller_path != controller_candidate
        or hashlib.sha256(controller_source).hexdigest()
        != controller_rows[0]["sha256"]
    ):
        raise _BootstrapError("committed source controller binding is invalid")
    return source_root, controller_path, controller_source


def _copy_bound_source(binding: _SourceBinding, destination: Path) -> _SourceBinding:
    destination.mkdir()
    for row in binding.inventory:
        target = destination.joinpath(*PurePosixPath(row["path"]).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(_read_bound(binding.source_root / row["path"]))
        os.chmod(target, 0o755 if row["git_mode"] == "100755" else 0o644)
    copied = _SourceBinding(
        source_root=destination,
        commit_oid=binding.commit_oid,
        tree_oid=binding.tree_oid,
        inventory=binding.inventory,
        inventory_sha256=binding.inventory_sha256,
    )
    _assert_source_inventory(copied)
    return copied


def _materialize_committed_source(
    repository: Path,
    bootstrap_root: Path,
    expected_commit_oid: str | None = None,
) -> _SourceBinding:
    repository = repository.resolve(strict=True)
    if _git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise _BootstrapError("release gate bootstrap requires a clean repository")
    commit_oid = _git(repository, "rev-parse", "HEAD")
    tree_oid = _git(repository, "rev-parse", "HEAD^{tree}")
    if (
        re.fullmatch(r"[0-9a-f]{40}", commit_oid) is None
        or re.fullmatch(r"[0-9a-f]{40}", tree_oid) is None
    ):
        raise _BootstrapError("release gate bootstrap repository identity is invalid")
    if expected_commit_oid is not None and commit_oid != expected_commit_oid:
        raise _BootstrapError("checkout HEAD does not match the event commit")
    git_entries = _assert_regular_git_tree(repository, commit_oid)
    blob_payloads = _git_blob_payloads(repository, git_entries)
    _assert_repository_identity(repository, commit_oid, tree_oid)

    archive = bootstrap_root / "committed-source.tar"
    staging = bootstrap_root / "committed-source"
    if archive.exists() or staging.exists():
        raise _BootstrapError("committed source destination already exists")
    _run(
        (
            "git",
            "-c",
            "core.autocrlf=false",
            "-C",
            str(repository),
            "archive",
            "--format=tar",
            "-o",
            str(archive),
            commit_oid,
        ),
        cwd=repository,
        env=_base_environment(),
    )
    _assert_repository_identity(repository, commit_oid, tree_oid)
    staging.mkdir()
    _safe_extract_archive(archive, staging)
    _assert_repository_identity(repository, commit_oid, tree_oid)
    if any(
        _read_bound(staging / entry["path"]) != blob_payloads[entry["path"]]
        for entry in git_entries
    ):
        raise _BootstrapError("committed source archive differs from Git blobs")
    inventory, inventory_sha256 = _build_source_inventory(staging, git_entries)
    return _SourceBinding(
        source_root=staging,
        commit_oid=commit_oid,
        tree_oid=tree_oid,
        inventory=inventory,
        inventory_sha256=inventory_sha256,
    )


def _wheel_inventory(
    wheel: Path,
    *,
    allowed_startup_surfaces: frozenset[str] = frozenset(),
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with zipfile.ZipFile(io.BytesIO(_read_bound(wheel))) as archive:
        infos = archive.infolist()
        if len(infos) > 100_000:
            raise _BootstrapError("bootstrap wheel inventory is oversized")
        seen: set[str] = set()
        for info in infos:
            pure = PurePosixPath(info.filename)
            if (
                pure.is_absolute()
                or any(part in {"", ".", ".."} for part in pure.parts)
                or info.is_dir()
                or info.filename in seen
                or info.file_size > _MAX_BOOTSTRAP_FILE
            ):
                if info.is_dir() and not pure.is_absolute() and ".." not in pure.parts:
                    continue
                raise _BootstrapError("bootstrap wheel inventory is unsafe")
            seen.add(info.filename)
            basename = pure.name.casefold()
            if (
                basename.endswith((".pth", ".egg-link"))
                or basename in {
                "sitecustomize.py",
                "usercustomize.py",
                }
            ) and info.filename not in allowed_startup_surfaces:
                raise _BootstrapError("bootstrap wheel contains a Python startup surface")
            data = archive.read(info)
            rows.append(
                {
                    "path": info.filename,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    return sorted(rows, key=lambda row: str(row["path"]))


class _StartupSurfacePolicy(NamedTuple):
    install: bool
    allowed_startup_surfaces: tuple[str, ...]


def _startup_surface_policy(name: object, version: object) -> _StartupSurfacePolicy:
    key = (re.sub(r"[-_.]+", "-", str(name)).casefold(), str(version))
    hooks = {
        ("setuptools", "83.0.0"): ("distutils-precedence.pth",),
        ("coverage", "7.15.2"): ("a1_coverage.pth",),
    }.get(key, ())
    return _StartupSurfacePolicy(
        install=not hooks,
        allowed_startup_surfaces=hooks,
    )


def _audit_local_wheelhouse(
    wheelhouse: Path,
    lock_rows: Mapping[tuple[str, str], Mapping[str, Any]],
) -> list[dict[str, object]]:
    root_metadata = wheelhouse.lstat()
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or _is_reparse(root_metadata)
    ):
        raise _BootstrapError("local wheelhouse is unsafe")
    candidates: dict[str, tuple[Mapping[str, Any], Mapping[str, str]]] = {}
    for locked in lock_rows.values():
        for candidate in locked["wheels"]:
            filename = candidate["name"]
            if filename in candidates:
                raise _BootstrapError("selected lock wheel filenames are ambiguous")
            candidates[filename] = (locked, candidate)
    observed: set[tuple[str, str]] = set()
    artifacts: list[dict[str, object]] = []
    entries = sorted(wheelhouse.iterdir(), key=lambda path: path.name)
    if len(entries) != len(lock_rows):
        raise _BootstrapError("local wheelhouse closure is incomplete")
    for wheel in entries:
        metadata = wheel.lstat()
        selected = candidates.get(wheel.name)
        if (
            selected is None
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
            or wheel.suffix.casefold() != ".whl"
        ):
            raise _BootstrapError("local wheelhouse closure is unsafe")
        locked, candidate = selected
        key = (
            re.sub(r"[-_.]+", "-", str(locked["name"])).casefold(),
            str(locked["version"]),
        )
        if key in observed:
            raise _BootstrapError("local wheelhouse closure is ambiguous")
        sha256 = hashlib.sha256(_read_bound(wheel)).hexdigest()
        if sha256 != candidate["sha256"]:
            raise _BootstrapError("local wheelhouse artifact hash mismatch")
        observed.add(key)
        policy = _startup_surface_policy(locked["name"], locked["version"])
        files = _wheel_inventory(
            wheel,
            allowed_startup_surfaces=frozenset(policy.allowed_startup_surfaces),
        )
        artifacts.append(
            {
                "name": locked["name"],
                "version": locked["version"],
                "url": candidate["url"],
                "sha256": sha256,
                "wheel_path": str(wheel),
                "files": files,
                "install": policy.install,
                "allowed_startup_surfaces": list(policy.allowed_startup_surfaces),
            }
        )
    if observed != set(lock_rows):
        raise _BootstrapError("local wheelhouse closure is incomplete")
    return sorted(artifacts, key=lambda row: str(row["name"]).casefold())


def _validate_locked_artifact(
    artifact: Mapping[str, object],
    locked: Mapping[str, Any],
    manifest_root: Path,
) -> None:
    if set(artifact) != {
        "name",
        "version",
        "url",
        "sha256",
        "wheel_path",
        "files",
        "install",
        "allowed_startup_surfaces",
    }:
        raise _BootstrapError("locked artifact policy validation failed")
    policy = _startup_surface_policy(locked.get("name"), locked.get("version"))
    expected_hooks = list(policy.allowed_startup_surfaces)
    if (
        artifact["name"] != locked.get("name")
        or artifact["version"] != locked.get("version")
        or artifact["install"] is not policy.install
        or artifact["allowed_startup_surfaces"] != expected_hooks
    ):
        raise _BootstrapError("locked artifact policy validation failed")
    candidates = locked.get("wheels")
    candidate = next(
        (
            row
            for row in candidates
            if isinstance(row, dict)
            and row.get("name") == Path(str(artifact["wheel_path"])).name
            and row.get("url") == artifact["url"]
            and row.get("sha256") == artifact["sha256"]
        ),
        None,
    ) if isinstance(candidates, list) else None
    if candidate is None:
        raise _BootstrapError("locked artifact policy validation failed")
    wheel_path = Path(str(artifact["wheel_path"])).resolve(strict=True)
    if manifest_root not in wheel_path.parents:
        raise _BootstrapError("locked artifact policy validation failed")
    wheel_source = _read_bound(wheel_path)
    if (
        hashlib.sha256(wheel_source).hexdigest() != artifact["sha256"]
        or _wheel_inventory(
            wheel_path,
            allowed_startup_surfaces=frozenset(policy.allowed_startup_surfaces),
        )
        != artifact["files"]
    ):
        raise _BootstrapError("locked artifact policy validation failed")


def _extract_locked_build_backend(
    artifact: Mapping[str, object], destination: Path
) -> Path:
    return _extract_locked_python_overlay((artifact,), destination)


def _extract_locked_python_overlay(
    artifacts: Sequence[Mapping[str, object]], destination: Path
) -> Path:
    policies = [
        _startup_surface_policy(artifact.get("name"), artifact.get("version"))
        for artifact in artifacts
    ]
    if (
        not artifacts
        or len(
            {
                (
                    re.sub(r"[-_.]+", "-", str(artifact.get("name", ""))).casefold(),
                    str(artifact.get("version", "")),
                )
                for artifact in artifacts
            }
        )
        != len(artifacts)
        or any(
            policy.install
            or artifact.get("install") is not policy.install
            or artifact.get("allowed_startup_surfaces")
            != list(policy.allowed_startup_surfaces)
            for artifact, policy in zip(artifacts, policies, strict=True)
        )
    ):
        raise _BootstrapError("locked Python overlay artifact set is invalid")
    destination.mkdir()
    for artifact, policy in zip(artifacts, policies, strict=True):
        wheel = Path(str(artifact.get("wheel_path", "")))
        allowed = frozenset(policy.allowed_startup_surfaces)
        if _wheel_inventory(
            wheel, allowed_startup_surfaces=allowed
        ) != artifact.get("files"):
            raise _BootstrapError("locked Python overlay artifact changed")
        with zipfile.ZipFile(io.BytesIO(_read_bound(wheel))) as archive:
            for info in archive.infolist():
                pure = PurePosixPath(info.filename)
                if info.is_dir() or info.filename in allowed:
                    continue
                mode = info.external_attr >> 16
                if mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                    raise _BootstrapError("locked Python overlay archive is unsafe")
                target = destination.joinpath(*pure.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(archive.read(info))
                os.chmod(target, 0o755 if mode & 0o111 else 0o644)
    if list(destination.rglob("*.pth")):
        raise _BootstrapError("locked Python overlay retained startup surface")
    _assert_extracted_python_overlay(artifacts, destination)
    return destination


def _assert_extracted_build_backend(
    artifact: Mapping[str, object], destination: Path
) -> None:
    _assert_extracted_python_overlay((artifact,), destination)


def _assert_extracted_python_overlay(
    artifacts: Sequence[Mapping[str, object]], destination: Path
) -> None:
    expected: dict[str, tuple[object, object]] = {}
    for artifact in artifacts:
        policy = _startup_surface_policy(artifact.get("name"), artifact.get("version"))
        if (
            policy.install
            or artifact.get("install") is not policy.install
            or artifact.get("allowed_startup_surfaces")
            != list(policy.allowed_startup_surfaces)
        ):
            raise _BootstrapError("locked Python overlay policy changed")
        raw_files = artifact.get("files")
        if not isinstance(raw_files, list):
            raise _BootstrapError("locked Python overlay inventory is invalid")
        for row in raw_files:
            if (
                isinstance(row, dict)
                and row.get("path") not in policy.allowed_startup_surfaces
            ):
                path = str(row["path"])
                if path in expected:
                    raise _BootstrapError("locked Python overlay paths collide")
                expected[path] = (row["size"], row["sha256"])
    observed: dict[str, tuple[int, str]] = {}
    for path in destination.rglob("*"):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
        ):
            raise _BootstrapError("locked build backend extraction is unsafe")
        relative = path.relative_to(destination).as_posix()
        source = _read_bound(path)
        observed[relative] = (len(source), hashlib.sha256(source).hexdigest())
    if observed != expected:
        raise _BootstrapError("locked Python overlay extraction changed")


def _purge_runtime_bytecode(environment_root: Path) -> None:
    for path in sorted(environment_root.rglob("*.pyc"), key=lambda item: len(item.parts), reverse=True):
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise _BootstrapError("runtime bytecode cleanup found unsafe payload")
        path.unlink()
    for path in sorted(
        environment_root.rglob("__pycache__"),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise _BootstrapError("runtime bytecode cleanup found unsafe directory")
        path.rmdir()


def _report_artifacts(
    report_path: Path,
    lock_rows: Mapping[tuple[str, str], Mapping[str, Any]],
    root: Path,
    seeded: tuple[Mapping[str, object], ...] = (),
) -> list[dict[str, object]]:
    try:
        report = json.loads(_read_bound(report_path), object_pairs_hook=_closed_object)
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise _BootstrapError("pip bootstrap report is invalid") from exc
    installs = report.get("install") if isinstance(report, dict) else None
    if not isinstance(installs, list) or len(installs) > len(lock_rows):
        raise _BootstrapError("pip bootstrap report package set is invalid")
    artifacts: list[dict[str, object]] = [dict(row) for row in seeded]
    observed: set[tuple[str, str]] = set()
    for row in artifacts:
        key = (
            re.sub(r"[-_.]+", "-", str(row.get("name", ""))).casefold(),
            str(row.get("version", "")),
        )
        locked = lock_rows.get(key)
        if (
            locked is None
            or key in observed
            or (row.get("url"), row.get("sha256"))
            not in {(item["url"], item["sha256"]) for item in locked["wheels"]}
        ):
            raise _BootstrapError("seeded bootstrap artifact differs from selected lock")
        observed.add(key)
    artifact_root = root / "artifacts"
    artifact_root.mkdir()
    for install in installs:
        metadata = install.get("metadata") if isinstance(install, dict) else None
        download = install.get("download_info") if isinstance(install, dict) else None
        archive_info = download.get("archive_info") if isinstance(download, dict) else None
        hashes = archive_info.get("hashes") if isinstance(archive_info, dict) else None
        name = metadata.get("name") if isinstance(metadata, dict) else None
        version = metadata.get("version") if isinstance(metadata, dict) else None
        url = download.get("url") if isinstance(download, dict) else None
        sha256 = hashes.get("sha256") if isinstance(hashes, dict) else None
        if not all(isinstance(value, str) for value in (name, version, url, sha256)):
            raise _BootstrapError("pip bootstrap report artifact is invalid")
        key = (re.sub(r"[-_.]+", "-", name).casefold(), version)
        locked = lock_rows.get(key)
        if locked is None:
            raise _BootstrapError("pip bootstrap report differs from selected lock")
        candidates = locked["wheels"]
        candidate = next(
            (
                row
                for row in candidates
                if row["url"] == url and row["sha256"] == sha256
            ),
            None,
        )
        if candidate is None:
            raise _BootstrapError("pip selected artifact differs from selected lock")
        if key in observed:
            seeded_row = next(
                row
                for row in artifacts
                if (
                    re.sub(r"[-_.]+", "-", str(row["name"])).casefold(),
                    str(row["version"]),
                )
                == key
            )
            if seeded_row.get("url") != url or seeded_row.get("sha256") != sha256:
                raise _BootstrapError("pip bootstrap report contradicts seeded artifact")
            continue
        observed.add(key)
        destination = artifact_root / f"{len(artifacts):02d}-{candidate['name']}"
        _download(url, destination, sha256)
        artifacts.append(
            {
                "name": locked["name"],
                "version": version,
                "url": url,
                "sha256": sha256,
                "wheel_path": str(destination),
                "files": _wheel_inventory(destination),
            }
        )
    if observed != set(lock_rows):
        raise _BootstrapError("pip bootstrap report omits selected lock packages")
    return sorted(artifacts, key=lambda row: str(row["name"]).casefold())


def _bootstrap_environment(
    repository: Path,
    bootstrap_root: Path,
) -> _RuntimeBootstrapBinding:
    repository = repository.resolve(strict=True)
    source_binding = _materialize_committed_source(
        repository,
        bootstrap_root,
        os.environ.get("GITHUB_SHA") or None,
    )
    staging = source_binding.source_root
    commit_oid = source_binding.commit_oid
    tree_oid = source_binding.tree_oid
    lock_path, lock_document, lock_source = _selected_lock(staging)
    source_lock_binding = _bootstrap_lock_binding(lock_path, lock_source)
    canonical_lock, canonical_lock_binding = _materialize_bootstrap_lock(
        bootstrap_root,
        lock_source,
    )
    lock_rows = _lock_rows(lock_document)
    environment_root = bootstrap_root / "environment"
    venv.EnvBuilder(with_pip=False, clear=False, symlinks=False).create(environment_root)
    python = _venv_python(environment_root)
    if not python.is_file():
        raise _BootstrapError("release gate bootstrap interpreter is missing")
    environment = _base_environment()
    environment.update(
        {
            "PIP_CACHE_DIR": str(bootstrap_root / "pip-cache"),
            "TEMP": str(bootstrap_root / "temp"),
            "TMP": str(bootstrap_root / "temp"),
            "TMPDIR": str(bootstrap_root / "temp"),
            "VIRTUAL_ENV": str(environment_root),
        }
    )
    for name in ("pip-cache", "temp"):
        (bootstrap_root / name).mkdir()
    _bootstrap_pip(python, lock_rows, bootstrap_root, environment)
    wheelhouse = bootstrap_root / "dependency-wheels"
    wheelhouse.mkdir()
    with (
        _bootstrap_lock_execution_lease(
            lock_path,
            lock_source,
            source_lock_binding,
        ),
        _bootstrap_lock_execution_lease(
            canonical_lock,
            lock_source,
            canonical_lock_binding,
        ),
    ):
        _run(
            (
                str(python),
                "-m",
                "pip",
                "download",
                "--require-virtualenv",
                "--no-deps",
                "--only-binary=:all:",
                "--dest",
                str(wheelhouse),
                "-r",
                str(canonical_lock),
            ),
            cwd=bootstrap_root,
            env=environment,
        )
    artifacts = _audit_local_wheelhouse(wheelhouse, lock_rows)
    build_backend_artifacts = [
        row for row in artifacts if row.get("install") is False
    ]
    if len(build_backend_artifacts) != 2:
        raise _BootstrapError("locked Python overlay artifact set is incomplete")
    build_backend_root = _extract_locked_python_overlay(
        build_backend_artifacts, bootstrap_root / "build-backend"
    )
    environment["PYTHONPATH"] = str(build_backend_root)
    install_artifacts = [row for row in artifacts if row.get("install") is True]
    _run(
        (
            str(python),
            "-m",
            "pip",
            "install",
            "--require-virtualenv",
            "--no-index",
            "--no-deps",
            *(str(Path(str(row["wheel_path"]))) for row in install_artifacts),
        ),
        cwd=bootstrap_root,
        env=environment,
    )
    _assert_repository_identity(repository, commit_oid, tree_oid)
    build_binding = _copy_bound_source(
        source_binding, bootstrap_root / "committed-build-source"
    )
    local_wheels = bootstrap_root / "local-wheel"
    local_wheels.mkdir()
    _run(
        (
            str(python),
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(local_wheels),
            str(build_binding.source_root),
        ),
        cwd=bootstrap_root,
        env=environment,
    )
    wheels = list(local_wheels.glob("*.whl"))
    if len(wheels) != 1:
        raise _BootstrapError("local committed wheel build is ambiguous")
    local_wheel = wheels[0]
    local_sha256 = hashlib.sha256(_read_bound(local_wheel)).hexdigest()
    local_files = _wheel_inventory(local_wheel)
    _assert_source_inventory(source_binding)
    _run(
        (str(python), "-m", "pip", "install", "--no-deps", str(local_wheel)),
        cwd=bootstrap_root,
        env=environment,
    )
    _purge_runtime_bytecode(environment_root)
    sentinel = uuid.uuid4().hex + uuid.uuid4().hex
    manifest: dict[str, object] = {
        "schema_version": 1,
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "repository": str(repository),
        "commit_oid": commit_oid,
        "tree_oid": tree_oid,
        "source_inventory": list(source_binding.inventory),
        "source_inventory_sha256": source_binding.inventory_sha256,
        "build_backend_root": str(build_backend_root),
        "environment_root": str(environment_root),
        "lock_sha256": hashlib.sha256(lock_source).hexdigest(),
        "sentinel_sha256": hashlib.sha256(sentinel.encode("ascii")).hexdigest(),
        "artifacts": artifacts,
        "local_project": {
            "name": "hsconfig",
            "version": _project_version(staging),
            "wheel_path": str(local_wheel),
            "sha256": local_sha256,
            "files": local_files,
            "source_inventory_sha256": source_binding.inventory_sha256,
        },
    }
    manifest_path = bootstrap_root / "runtime-manifest.json"
    manifest_bytes = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    return _RuntimeBootstrapBinding(
        python=python,
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        sentinel=sentinel,
    )


def _child_binding(args: argparse.Namespace) -> bool:
    sentinel = os.environ.get(_SENTINEL, "")
    manifest_name = os.environ.get(_MANIFEST, "")
    expected_digest = os.environ.get(_MANIFEST_DIGEST, "")
    if re.fullmatch(r"[0-9a-f]{64}", sentinel) is None or re.fullmatch(
        r"[0-9a-f]{64}", expected_digest
    ) is None:
        return False
    try:
        channel = sys.stdin.buffer.readline(66)
        if channel != sentinel.encode("ascii") + b"\n":
            return False
        manifest_path = Path(manifest_name)
        source = _read_bound(manifest_path, 64 * 1024 * 1024)
        if hashlib.sha256(source).hexdigest() != expected_digest:
            return False
        manifest = json.loads(source, object_pairs_hook=_closed_object)
        if not isinstance(manifest, dict) or set(manifest) != {
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
            return False
        environment_root_source = Path(manifest["environment_root"])
        environment_metadata = environment_root_source.lstat()
        environment_root = environment_root_source.resolve(strict=True)
        executable = Path(sys.executable).resolve(strict=True)
        repository = args.repo.resolve(strict=True)
        manifest_root = manifest_path.parent.resolve(strict=True)
        source_root = (manifest_root / "committed-source").resolve(strict=True)
        build_backend_source = Path(str(manifest["build_backend_root"]))
        build_backend_metadata = build_backend_source.lstat()
        build_backend_root = build_backend_source.resolve(strict=True)
        raw_inventory = manifest["source_inventory"]
        if not isinstance(raw_inventory, list):
            return False
        inventory: list[dict[str, str]] = []
        for row in raw_inventory:
            if (
                not isinstance(row, dict)
                or set(row) != {"path", "sha256", "git_mode"}
                or not isinstance(row["path"], str)
                or row["git_mode"] not in {"100644", "100755"}
                or re.fullmatch(r"[0-9a-f]{64}", str(row["sha256"])) is None
            ):
                return False
            inventory.append(dict(row))
        controller_path = Path(__file__).resolve(strict=True)
        committed_controller = (
            source_root / "scripts" / "check_release_gate.py"
        ).resolve(strict=True)
        controller_row = next(
            (
                row
                for row in inventory
                if row["path"] == "scripts/check_release_gate.py"
            ),
            None,
        )
        if (
            controller_path != committed_controller
            or controller_row is None
            or hashlib.sha256(_read_bound(controller_path)).hexdigest()
            != controller_row["sha256"]
        ):
            return False
        source_binding = _SourceBinding(
            source_root=source_root,
            commit_oid=str(manifest["commit_oid"]),
            tree_oid=str(manifest["tree_oid"]),
            inventory=tuple(inventory),
            inventory_sha256=str(manifest["source_inventory_sha256"]),
        )
        _assert_source_inventory(source_binding)
        lock_path, lock_document, lock_source = _selected_lock(source_root)
        del lock_path
        lock_rows = _lock_rows(lock_document)
        if (
            manifest["schema_version"] != 1
            or manifest["repository"] != str(repository)
            or manifest_path.name != "runtime-manifest.json"
            or not stat.S_ISDIR(environment_metadata.st_mode)
            or stat.S_ISLNK(environment_metadata.st_mode)
            or _is_reparse(environment_metadata)
            or environment_root != manifest_root / "environment"
            or not stat.S_ISDIR(build_backend_metadata.st_mode)
            or stat.S_ISLNK(build_backend_metadata.st_mode)
            or _is_reparse(build_backend_metadata)
            or build_backend_root != manifest_root / "build-backend"
            or manifest["commit_oid"] != _git(repository, "rev-parse", "HEAD")
            or manifest["tree_oid"] != _git(repository, "rev-parse", "HEAD^{tree}")
            or _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
            or inventory != sorted(inventory, key=lambda row: row["path"])
            or len({row["path"] for row in inventory}) != len(inventory)
            or re.fullmatch(
                r"[0-9a-f]{64}", str(manifest["source_inventory_sha256"])
            )
            is None
            or manifest["lock_sha256"] != hashlib.sha256(lock_source).hexdigest()
        ):
            return False
        artifacts = manifest["artifacts"]
        local = manifest["local_project"]
        if not isinstance(artifacts, list) or len(artifacts) != 43 or not isinstance(local, dict):
            return False
        observed: set[tuple[str, str]] = set()
        for row in artifacts:
            if not isinstance(row, dict) or set(row) != {
                "name",
                "version",
                "url",
                "sha256",
                "wheel_path",
                "files",
                "install",
                "allowed_startup_surfaces",
            }:
                return False
            key = (
                re.sub(r"[-_.]+", "-", str(row["name"])).casefold(),
                str(row["version"]),
            )
            locked = lock_rows.get(key)
            if locked is None or key in observed:
                return False
            observed.add(key)
            _validate_locked_artifact(row, locked, manifest_root)
        if observed != set(lock_rows) or set(local) != {
            "name",
            "version",
            "wheel_path",
            "sha256",
            "files",
            "source_inventory_sha256",
        }:
            return False
        _assert_extracted_python_overlay(
            [row for row in artifacts if row["install"] is False],
            build_backend_root,
        )
        local_wheel = Path(str(local["wheel_path"])).resolve(strict=True)
        local_source = _read_bound(local_wheel)
        if (
            local["name"] != "hsconfig"
            or local["version"] != _project_version(source_root)
            or local["source_inventory_sha256"]
            != manifest["source_inventory_sha256"]
            or manifest_root not in local_wheel.parents
            or hashlib.sha256(local_source).hexdigest() != local["sha256"]
            or _wheel_inventory(local_wheel) != local["files"]
        ):
            return False
    except (
        OSError,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        _BootstrapError,
    ):
        return False
    return (
        hashlib.sha256(sentinel.encode("ascii")).hexdigest()
        == manifest.get("sentinel_sha256")
        and environment_root in executable.parents
        and manifest.get("python_minor")
        == f"{sys.version_info.major}.{sys.version_info.minor}"
    )


def _child_main(args: argparse.Namespace) -> int:
    if args.locked_check == "full-tests-and-coverage":
        from scripts import run_coverage_gate  # noqa: PLC0415

        return run_coverage_gate.main()

    from hsconfig.release_gate import (  # noqa: PLC0415
        _validate_repository,
        check_repository_hygiene,
        run_release_gate,
        scan_publishable_content,
    )

    if args.internal_check == "publishable_path_scan":
        _validate_repository(
            args.repo,
            args.outputs,
            args.tree_mode,
            owner_repository=args.owner_repo,
        )
        document = scan_publishable_content(
            repository=args.repo,
            outputs_root=args.outputs,
            tree_mode=args.tree_mode,
        )
        _emit(document)
        return 0 if document["passed"] else 1
    if args.internal_check == "repository_hygiene":
        _validate_repository(
            args.repo,
            args.outputs,
            args.tree_mode,
            owner_repository=args.owner_repo,
        )
        document = check_repository_hygiene(args.repo, args.outputs)
        _emit(document)
        return 0 if document["passed"] else 1
    result = run_release_gate(
        repository=args.repo,
        outputs_root=args.outputs,
        tree_mode=args.tree_mode,
        owner_repository=args.owner_repo,
    )
    _emit(result.to_document())
    return 0 if result.passed else 1


def _delete_posix_tree(path: Path, identity: tuple[int, int]) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != identity:
            raise _BootstrapError("bootstrap quarantine identity changed")

        def empty(directory: int) -> None:
            for name in os.listdir(directory):
                metadata = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
                    child = os.open(
                        name,
                        flags,
                        dir_fd=directory,
                    )
                    try:
                        empty(child)
                    finally:
                        os.close(child)
                    os.rmdir(name, dir_fd=directory)
                else:
                    os.unlink(name, dir_fd=directory)

        empty(descriptor)
    finally:
        os.close(descriptor)
    os.rmdir(path)


def _delete_windows_entry(path: Path, identity: tuple[int, int] | None = None) -> None:
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
        raise _BootstrapError("bootstrap quarantine handle cannot be opened")
    try:
        before = path.lstat()
        if identity is not None and (before.st_dev, before.st_ino) != identity:
            raise _BootstrapError("bootstrap quarantine identity changed")
        if (
            stat.S_ISDIR(before.st_mode)
            and not stat.S_ISLNK(before.st_mode)
            and not _is_reparse(before)
        ):
            for entry in list(os.scandir(path)):
                child = Path(entry.path)
                metadata = child.lstat()
                _delete_windows_entry(child, (metadata.st_dev, metadata.st_ino))
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
            raise _BootstrapError("bootstrap quarantine identity changed")
        disposition = wintypes.BOOL(True)
        if not kernel32.SetFileInformationByHandle(
            handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)
        ):
            raise _BootstrapError("bootstrap quarantine delete disposition failed")
    finally:
        kernel32.CloseHandle(handle)
    if path.exists() or path.is_symlink():
        raise _BootstrapError("bootstrap cleanup left residue")


def _delete_owned_bootstrap_tree(path: Path, identity: tuple[int, int]) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or _is_reparse(metadata)
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        raise _BootstrapError("bootstrap quarantine identity changed")
    if os.name == "nt":
        _delete_windows_entry(path, identity)
    else:
        _delete_posix_tree(path, identity)


def _cleanup_bootstrap_root(root: Path, identity: tuple[int, int]) -> None:
    try:
        metadata = root.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or _is_reparse(metadata)
            or (metadata.st_dev, metadata.st_ino) != identity
        ):
            raise _BootstrapError("bootstrap root ownership was lost")
        quarantine = root.with_name(f".hsconfig-bootstrap-quarantine-{uuid.uuid4().hex}")
        os.replace(root, quarantine)
        moved = quarantine.lstat()
        if (moved.st_dev, moved.st_ino) != identity:
            raise _BootstrapError("bootstrap quarantine identity changed")
        interrupted: BaseException | None = None
        for _attempt in range(3):
            try:
                _delete_owned_bootstrap_tree(quarantine, identity)
                break
            except (KeyboardInterrupt, SystemExit) as exc:
                interrupted = exc
                continue
        if quarantine.exists() or quarantine.is_symlink():
            if interrupted is not None:
                raise interrupted
            raise _BootstrapError("bootstrap cleanup left residue")
        if interrupted is not None:
            raise interrupted
    except _BootstrapError:
        raise
    except OSError as exc:
        raise _BootstrapError("bootstrap cleanup failed") from exc


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
        raise _BootstrapError("release gate child subreaper setup failed")


class _BootstrapProcessTreeLease:
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
            _terminate_unleased_process(self.process)
            raise _BootstrapError("release gate child isolation failed")
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
            _terminate_unleased_process(self.process)
            raise _BootstrapError("release gate child isolation failed")
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


def _terminate_unleased_process(process: subprocess.Popen[bytes]) -> None:
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=30)
    finally:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass


def _run_bound_child(
    python: Path,
    invocation_directory: Path,
    environment: Mapping[str, str],
    argv: list[str],
    sentinel: str,
    *,
    timeout: int = _BOOTSTRAP_CHILD_TIMEOUT_SECONDS,
    allow_locked_coverage_exit_two: bool = False,
    controller_path: Path | None = None,
) -> tuple[int, dict[str, object]]:
    child_environment = dict(environment)
    child_cwd = invocation_directory.resolve(strict=True)
    controller_source: bytes
    if controller_path is None:
        manifest_name = child_environment.get(_MANIFEST, "")
        manifest_digest = child_environment.get(_MANIFEST_DIGEST, "")
        if re.fullmatch(r"[0-9a-f]{64}", manifest_digest) is None:
            raise _BootstrapError("release gate child manifest binding is missing")
        manifest_path = Path(manifest_name).resolve(strict=True)
        manifest_source = _read_bound(manifest_path, 64 * 1024 * 1024)
        if hashlib.sha256(manifest_source).hexdigest() != manifest_digest:
            raise _BootstrapError("release gate child manifest binding changed")
        manifest_document = json.loads(
            manifest_source, object_pairs_hook=_closed_object
        )
        source_root, controller_path, controller_source = _bound_committed_controller(
            manifest_path, manifest_document
        )
        existing_pythonpath = child_environment.get("PYTHONPATH", "")
        child_environment["PYTHONPATH"] = str(source_root) + (
            os.pathsep + existing_pythonpath if existing_pythonpath else ""
        )
    else:
        controller_path = controller_path.resolve(strict=True)
        controller_source = _read_bound(controller_path, _MAX_CONTROLLER_SOURCE)
    if os.name != "nt":
        _enable_posix_subreaper()
    baseline = _linux_direct_children()
    platform_options: dict[str, object] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process: subprocess.Popen[bytes] | None = None
    lease: _BootstrapProcessTreeLease | None = None
    reader: threading.Thread | None = None
    reader_started = False
    captured: bytearray | None = None
    oversized: threading.Event | None = None
    reader_errors: list[BaseException] | None = None
    timed_out = False
    returncode = 2
    try:
        process = subprocess.Popen(
            (
                _process_tree_gate_interpreter(python),
                "-I",
                "-S",
                "-B",
                "-c",
                _GATED_CHILD_LAUNCHER,
            ),
            cwd=child_cwd,
            env=child_environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            shell=False,
            **platform_options,
        )
        lease = _BootstrapProcessTreeLease(process, baseline)
        captured = bytearray()
        oversized = threading.Event()
        reader_errors = []

        def drain() -> None:
            try:
                while True:
                    if process is None or process.stdout is None:
                        raise OSError("release gate child stdout disappeared")
                    chunk = process.stdout.read(8192)
                    if not chunk:
                        return
                    captured.extend(chunk)
                    if len(captured) > _MAX_CHILD_STDOUT:
                        oversized.set()
                        process.kill()
                        return
            except (OSError, ValueError) as exc:
                reader_errors.append(exc)
                try:
                    if process is not None:
                        process.kill()
                except OSError:
                    pass

        if process.stdin is None or process.stdout is None:
            raise _BootstrapError("release gate child pipes are unavailable")
        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        reader_started = True
        child_argv = (
            str(python),
            "-P",
            "-c",
            _VERIFIED_CONTROLLER_LAUNCHER,
            str(controller_path),
            *argv,
        )
        process.stdin.write(
            json.dumps(child_argv, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
        process.stdin.write(f"{len(controller_source)}\n".encode("ascii"))
        process.stdin.write(controller_source)
        process.stdin.write(sentinel.encode("ascii") + b"\n")
        process.stdin.close()
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        returncode = 2
    finally:
        if process is not None:
            if lease is not None:
                lease.terminate_remaining()
            else:
                _terminate_unleased_process(process)
            if reader is not None and reader_started:
                reader.join(timeout=30)
            for stream in (process.stdin, process.stdout):
                if stream is not None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass
    if reader is not None and reader_started and reader.is_alive():
        raise _BootstrapError("release gate child stdout did not close")
    if reader_errors is None or oversized is None or captured is None:
        raise _BootstrapError("release gate child transport setup failed")
    if reader_errors:
        raise _BootstrapError("release gate child stdout read failed")
    if oversized.is_set():
        raise _BootstrapError("release gate child stdout exceeded size limit")
    if timed_out:
        raise _BootstrapError("release gate child timed out")
    try:
        text = bytes(captured).decode("utf-8")
        if text.count("\n") != 1 or not text.endswith("\n"):
            raise ValueError("child output is not one line")
        document = json.loads(text, object_pairs_hook=_closed_object)
    except (UnicodeError, ValueError, json.JSONDecodeError) as exc:
        raise _BootstrapError("release gate child emitted invalid JSON") from exc
    allowed_returncodes = {0, 1, 2} if allow_locked_coverage_exit_two else {0, 1}
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("passed"), bool)
        or returncode not in allowed_returncodes
        or document["passed"] is not (returncode == 0)
    ):
        raise _BootstrapError("release gate child result contradicts exit status")
    return returncode, document


def _bootstrap_and_reexec(
    args: argparse.Namespace,
    argv: list[str],
) -> tuple[int, dict[str, object]]:
    invocation_directory = Path.cwd().resolve(strict=True)
    repository = args.repo.resolve()
    configured_temp = Path(tempfile.gettempdir()).resolve(strict=True)
    if configured_temp == repository or repository in configured_temp.parents:
        raise _BootstrapError("bootstrap root must be outside repository")
    root: Path | None = None
    identity: tuple[int, int] | None = None
    try:
        root = Path(tempfile.mkdtemp(prefix="hsconfig-release-bootstrap-", dir=configured_temp))
        metadata = root.lstat()
        identity = (metadata.st_dev, metadata.st_ino)
        runtime_binding = _bootstrap_environment(repository, root)
        manifest_source = _read_bound(
            runtime_binding.manifest_path, 64 * 1024 * 1024
        )
        if (
            hashlib.sha256(manifest_source).hexdigest()
            != runtime_binding.manifest_sha256
        ):
            raise _BootstrapError("release gate child manifest binding changed")
        manifest_document = json.loads(
            manifest_source, object_pairs_hook=_closed_object
        )
        environment = _base_environment()
        environment.update(
            {
                _SENTINEL: runtime_binding.sentinel,
                _MANIFEST: str(runtime_binding.manifest_path),
                _MANIFEST_DIGEST: runtime_binding.manifest_sha256,
                "VIRTUAL_ENV": str(runtime_binding.python.parent.parent),
            }
        )
        build_backend_root = manifest_document.get("build_backend_root")
        if isinstance(build_backend_root, str):
            environment["PYTHONPATH"] = build_backend_root
        result = _run_bound_child(
            runtime_binding.python,
            invocation_directory,
            environment,
            argv,
            runtime_binding.sentinel,
            allow_locked_coverage_exit_two=(
                args.locked_check == "full-tests-and-coverage"
                or args.internal_check is not None
                or args.tree_mode == "candidate"
            ),
        )
        return result
    finally:
        if root is not None and identity is not None:
            _cleanup_bootstrap_root(root, identity)


def _append_github_environment(path: Path, values: Mapping[str, str]) -> None:
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z0-9_]+", key) or "\n" in value or "\r" in value:
            raise _BootstrapError("CI baseline environment value is invalid")
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _write_source_inventory_manifest(root: Path, binding: _SourceBinding) -> Path:
    path = root / "source-inventory.json"
    document = {
        "schema_version": 1,
        "source_root": str(binding.source_root),
        "commit_oid": binding.commit_oid,
        "tree_oid": binding.tree_oid,
        "inventory": list(binding.inventory),
        "inventory_sha256": binding.inventory_sha256,
    }
    encoded = json.dumps(
        document,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    with path.open("xb") as handle:
        handle.write(encoded)
    return path


def _load_ci_source_binding(args: argparse.Namespace) -> _SourceBinding:
    repository = args.repo.resolve(strict=True)
    runner_temp_value = os.environ.get("RUNNER_TEMP", "")
    baseline_value = os.environ.get("HSCONFIG_CI_BASELINE_ROOT", "")
    source_value = os.environ.get("HSCONFIG_CI_SOURCE_ROOT", "")
    manifest_value = os.environ.get("HSCONFIG_CI_SOURCE_INVENTORY", "")
    commit_oid = os.environ.get("HSCONFIG_CI_COMMIT_OID", "")
    tree_oid = os.environ.get("HSCONFIG_CI_TREE_OID", "")
    inventory_sha256 = os.environ.get("HSCONFIG_CI_SOURCE_INVENTORY_SHA256", "")
    if (
        not all((runner_temp_value, baseline_value, source_value, manifest_value))
        or re.fullmatch(r"[0-9a-f]{40}", commit_oid) is None
        or re.fullmatch(r"[0-9a-f]{40}", tree_oid) is None
        or re.fullmatch(r"[0-9a-f]{64}", inventory_sha256) is None
    ):
        raise _BootstrapError("CI source binding environment is incomplete")
    runner_temp = Path(runner_temp_value).resolve(strict=True)
    baseline_root = Path(baseline_value).resolve(strict=True)
    source_root = Path(source_value).resolve(strict=True)
    manifest_path = Path(manifest_value).resolve(strict=True)
    if (
        baseline_root != runner_temp / "hsconfig-ci-source-baseline"
        or source_root != baseline_root / "committed-source"
        or manifest_path != baseline_root / "source-inventory.json"
    ):
        raise _BootstrapError("CI source binding path is invalid")
    try:
        document = json.loads(_read_bound(manifest_path), object_pairs_hook=_closed_object)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise _BootstrapError("CI source inventory manifest is invalid") from exc
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "source_root",
        "commit_oid",
        "tree_oid",
        "inventory",
        "inventory_sha256",
    }:
        raise _BootstrapError("CI source inventory manifest is invalid")
    raw_inventory = document["inventory"]
    if not isinstance(raw_inventory, list):
        raise _BootstrapError("CI source inventory manifest is invalid")
    inventory: list[dict[str, str]] = []
    for row in raw_inventory:
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "sha256", "git_mode"}
            or not isinstance(row["path"], str)
            or row["git_mode"] not in {"100644", "100755"}
            or re.fullmatch(r"[0-9a-f]{64}", str(row["sha256"])) is None
        ):
            raise _BootstrapError("CI source inventory manifest is invalid")
        inventory.append(dict(row))
    if (
        document["schema_version"] != 1
        or document["source_root"] != str(source_root)
        or document["commit_oid"] != commit_oid
        or document["tree_oid"] != tree_oid
        or document["inventory_sha256"] != inventory_sha256
        or inventory != sorted(inventory, key=lambda row: row["path"])
        or len({row["path"] for row in inventory}) != len(inventory)
    ):
        raise _BootstrapError("CI source inventory manifest binding changed")
    binding = _SourceBinding(
        source_root=source_root,
        commit_oid=commit_oid,
        tree_oid=tree_oid,
        inventory=tuple(inventory),
        inventory_sha256=inventory_sha256,
    )
    _assert_source_inventory(binding)
    _assert_repository_identity(repository, commit_oid, tree_oid)
    return binding


def _run_ci_source_revalidate(args: argparse.Namespace) -> int:
    binding = _load_ci_source_binding(args)
    _emit(
        {
            "passed": True,
            "final_release_ready": False,
            "version": _project_version(binding.source_root),
            "commit_oid": binding.commit_oid,
            "tree_oid": binding.tree_oid,
            "checks": ["ci_source_revalidate"],
            "errors": [],
        }
    )
    return 0


def _run_ci_wheelhouse_audit(args: argparse.Namespace) -> int:
    binding = _load_ci_source_binding(args)
    _lock_path, lock_document, _lock_source = _selected_lock(binding.source_root)
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    wheelhouse = (
        runner_temp / "hsconfig-locked-runtime" / "dependency-wheels"
    ).resolve(strict=True)
    artifacts = _audit_local_wheelhouse(wheelhouse, _lock_rows(lock_document))
    build_backend_artifacts = [row for row in artifacts if row.get("install") is False]
    if len(build_backend_artifacts) != 2:
        raise _BootstrapError("locked Python overlay artifact set is incomplete")
    build_backend_root = _extract_locked_python_overlay(
        build_backend_artifacts,
        runner_temp / "hsconfig-locked-runtime" / "build-backend",
    )
    _emit(
        {
            "passed": True,
            "final_release_ready": False,
            "version": _project_version(binding.source_root),
            "commit_oid": binding.commit_oid,
            "tree_oid": binding.tree_oid,
            "checks": ["ci_wheelhouse_audit"],
            "artifact_count": len(artifacts),
            "build_backend_root": str(build_backend_root),
            "errors": [],
        }
    )
    return 0


def _run_ci_source_baseline(args: argparse.Namespace) -> int:
    repository = args.repo.resolve(strict=True)
    runner_temp_value = os.environ.get("RUNNER_TEMP", "")
    github_sha = os.environ.get("GITHUB_SHA", "")
    github_environment_value = os.environ.get("GITHUB_ENV", "")
    if (
        not runner_temp_value
        or re.fullmatch(r"[0-9a-f]{40}", github_sha) is None
        or not github_environment_value
    ):
        raise _BootstrapError("CI baseline environment is incomplete")
    runner_temp = Path(runner_temp_value).resolve(strict=True)
    if runner_temp == repository or repository in runner_temp.parents:
        raise _BootstrapError("CI baseline root must be outside repository")
    root = runner_temp / "hsconfig-ci-source-baseline"
    if root.exists():
        raise _BootstrapError("CI baseline root already exists")
    root.mkdir()
    _append_github_environment(
        Path(github_environment_value),
        {"HSCONFIG_CI_BASELINE_ROOT": str(root)},
    )
    source_binding = _materialize_committed_source(
        repository,
        root,
        github_sha,
    )
    inventory_manifest = _write_source_inventory_manifest(root, source_binding)
    _append_github_environment(
        Path(github_environment_value),
        {
            "HSCONFIG_CI_SOURCE_ROOT": str(source_binding.source_root),
            "HSCONFIG_CI_COMMIT_OID": source_binding.commit_oid,
            "HSCONFIG_CI_TREE_OID": source_binding.tree_oid,
            "HSCONFIG_CI_SOURCE_INVENTORY": str(inventory_manifest),
            "HSCONFIG_CI_SOURCE_INVENTORY_SHA256": source_binding.inventory_sha256,
        },
    )
    _emit(
        {
            "passed": True,
            "final_release_ready": False,
            "version": _project_version(source_binding.source_root),
            "commit_oid": source_binding.commit_oid,
            "tree_oid": source_binding.tree_oid,
            "checks": ["ci_source_baseline"],
            "errors": [],
        }
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _parser().parse_args(args_list)
        if args.locked_check == "ci-source-baseline":
            return _run_ci_source_baseline(args)
        if args.locked_check == "ci-source-revalidate":
            return _run_ci_source_revalidate(args)
        if args.locked_check == "ci-wheelhouse-audit":
            return _run_ci_wheelhouse_audit(args)
        child_binding_requested = any(
            os.environ.get(name) for name in (_SENTINEL, _MANIFEST, _MANIFEST_DIGEST)
        )
        if _child_binding(args):
            return _child_main(args)
        if child_binding_requested:
            raise _BootstrapError("release gate child binding failed")
        returncode, document = _bootstrap_and_reexec(args, args_list)
        _emit(document)
        return returncode
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        try:
            version = _project_version(Path(args.repo).resolve()) if "args" in locals() else ""
        except BaseException:
            version = ""
        _emit(_failure(version, str(exc)))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
