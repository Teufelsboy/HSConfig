from __future__ import annotations

import argparse
import ast
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
from typing import Any, Mapping
from urllib.request import Request, urlopen
import uuid
import venv
import zipfile


# The documented parent remains stdlib-only and must not create checkout
# bytecode before the child has run repository hygiene.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
_SENTINEL = "HSCONFIG_RELEASE_GATE_BOOTSTRAP_SENTINEL"
_MANIFEST = "HSCONFIG_RUNTIME_MANIFEST"
_MANIFEST_DIGEST = "HSCONFIG_RUNTIME_MANIFEST_SHA256"
_MAX_BOOTSTRAP_FILE = 512 * 1024 * 1024
_MAX_CHILD_STDOUT = 1024 * 1024
_SUPPORTED_PYTHON_MINORS = {"3.11", "3.12"}
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_GATED_CHILD_LAUNCHER = (
    "import json,os,subprocess,sys; header=bytearray(); "
    "[(header.extend(chunk),None)[1] for chunk in iter(lambda:os.read(0,1),b'\\n')]; "
    "argv=json.loads(header); "
    "assert isinstance(argv,list) and argv and all(isinstance(x,str) for x in argv); "
    "raise SystemExit(subprocess.run(argv,stdin=sys.stdin.buffer).returncode)"
)


class _CliError(ValueError):
    pass


class _BootstrapError(RuntimeError):
    pass


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(getattr(metadata, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT)


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _CliError(f"argument_error:{message}")


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(description="Run the canonical local release gate.")
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--outputs", required=True, type=Path)
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
        env=environment,
    )
    return {
        "name": pip_rows[0]["name"],
        "version": pip_rows[0]["version"],
        "url": wheel["url"],
        "sha256": wheel["sha256"],
        "wheel_path": str(destination),
        "files": _wheel_inventory(destination),
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


def _wheel_inventory(wheel: Path) -> list[dict[str, object]]:
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
            data = archive.read(info)
            rows.append(
                {
                    "path": info.filename,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
    return sorted(rows, key=lambda row: str(row["path"]))


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


def _bootstrap_environment(repository: Path, bootstrap_root: Path) -> tuple[Path, Path, str]:
    repository = repository.resolve(strict=True)
    if _git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise _BootstrapError("release gate bootstrap requires a clean repository")
    commit_oid = _git(repository, "rev-parse", "HEAD")
    tree_oid = _git(repository, "rev-parse", "HEAD^{tree}")
    if re.fullmatch(r"[0-9a-f]{40}", commit_oid) is None or re.fullmatch(
        r"[0-9a-f]{40}", tree_oid
    ) is None:
        raise _BootstrapError("release gate bootstrap repository identity is invalid")
    lock_path, lock_document, lock_source = _selected_lock(repository)
    lock_rows = _lock_rows(lock_document)
    environment_root = bootstrap_root / "environment"
    venv.EnvBuilder(with_pip=True, clear=False, symlinks=False).create(environment_root)
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
    pip_artifact = _bootstrap_pip(python, lock_rows, bootstrap_root, environment)
    report_path = bootstrap_root / "pip-report.json"
    _run(
        (
            str(python),
            "-m",
            "pip",
            "install",
            "--require-virtualenv",
            "--no-deps",
            "-r",
            str(lock_path),
            "--report",
            str(report_path),
        ),
        cwd=bootstrap_root,
        env=environment,
    )
    artifacts = _report_artifacts(
        report_path,
        lock_rows,
        bootstrap_root,
        seeded=(pip_artifact,),
    )
    archive = bootstrap_root / "committed-source.tar"
    _run(
        (
            "git",
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
    if (
        _git(repository, "rev-parse", f"{commit_oid}^{{tree}}") != tree_oid
        or _git(repository, "rev-parse", "HEAD") != commit_oid
        or _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
    ):
        raise _BootstrapError("repository changed during committed source bootstrap")
    staging = bootstrap_root / "committed-source"
    staging.mkdir()
    _safe_extract_archive(archive, staging)
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
            str(staging),
        ),
        cwd=bootstrap_root,
        env=environment,
    )
    wheels = list(local_wheels.glob("*.whl"))
    if len(wheels) != 1:
        raise _BootstrapError("local committed wheel build is ambiguous")
    local_wheel = wheels[0]
    _run(
        (str(python), "-m", "pip", "install", "--no-deps", str(local_wheel)),
        cwd=bootstrap_root,
        env=environment,
    )
    _purge_runtime_bytecode(environment_root)
    local_sha256 = hashlib.sha256(_read_bound(local_wheel)).hexdigest()
    sentinel = uuid.uuid4().hex + uuid.uuid4().hex
    manifest: dict[str, object] = {
        "schema_version": 1,
        "python_minor": f"{sys.version_info.major}.{sys.version_info.minor}",
        "repository": str(repository),
        "commit_oid": commit_oid,
        "tree_oid": tree_oid,
        "environment_root": str(environment_root),
        "lock_sha256": hashlib.sha256(lock_source).hexdigest(),
        "sentinel_sha256": hashlib.sha256(sentinel.encode("ascii")).hexdigest(),
        "artifacts": artifacts,
        "local_project": {
            "name": "hsconfig",
            "version": _project_version(staging),
            "wheel_path": str(local_wheel),
            "sha256": local_sha256,
            "files": _wheel_inventory(local_wheel),
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
    return python, manifest_path, sentinel


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
        lock_path, lock_document, lock_source = _selected_lock(repository)
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
            or manifest["commit_oid"] != _git(repository, "rev-parse", "HEAD")
            or manifest["tree_oid"] != _git(repository, "rev-parse", "HEAD^{tree}")
            or _git(repository, "status", "--porcelain=v1", "--untracked-files=all")
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
                "name", "version", "url", "sha256", "wheel_path", "files"
            }:
                return False
            key = (
                re.sub(r"[-_.]+", "-", str(row["name"])).casefold(),
                str(row["version"]),
            )
            locked = lock_rows.get(key)
            if (
                locked is None
                or key in observed
                or (row["url"], row["sha256"])
                not in {(item["url"], item["sha256"]) for item in locked["wheels"]}
            ):
                return False
            observed.add(key)
            wheel_path = Path(str(row["wheel_path"])).resolve(strict=True)
            if manifest_root not in wheel_path.parents:
                return False
            wheel_source = _read_bound(wheel_path)
            if (
                hashlib.sha256(wheel_source).hexdigest() != row["sha256"]
                or _wheel_inventory(wheel_path) != row["files"]
            ):
                return False
        if observed != set(lock_rows) or set(local) != {
            "name", "version", "wheel_path", "sha256", "files"
        }:
            return False
        local_wheel = Path(str(local["wheel_path"])).resolve(strict=True)
        local_source = _read_bound(local_wheel)
        if (
            local["name"] != "hsconfig"
            or local["version"] != _project_version(repository)
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
    from hsconfig.release_gate import (  # noqa: PLC0415
        check_repository_hygiene,
        run_release_gate,
        scan_publishable_content,
    )

    if args.internal_check == "publishable_path_scan":
        document = scan_publishable_content(
            repository=args.repo,
            outputs_root=args.outputs,
            tree_mode=args.tree_mode,
        )
        _emit(document)
        return 0 if document["passed"] else 1
    if args.internal_check == "repository_hygiene":
        document = check_repository_hygiene(args.repo, args.outputs)
        _emit(document)
        return 0 if document["passed"] else 1
    result = run_release_gate(
        repository=args.repo,
        outputs_root=args.outputs,
        tree_mode=args.tree_mode,
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
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass


def _run_bound_child(
    python: Path,
    repository: Path,
    environment: Mapping[str, str],
    argv: list[str],
    sentinel: str,
    *,
    timeout: int = 7200,
) -> tuple[int, dict[str, object]]:
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
            (str(python), "-c", _GATED_CHILD_LAUNCHER),
            cwd=repository,
            env=dict(environment),
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
        child_argv = (str(python), str(Path(__file__).resolve()), *argv)
        process.stdin.write(
            json.dumps(child_argv, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
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
    if (
        not isinstance(document, dict)
        or not isinstance(document.get("passed"), bool)
        or returncode not in {0, 1}
        or document["passed"] is not (returncode == 0)
    ):
        raise _BootstrapError("release gate child result contradicts exit status")
    return returncode, document


def _bootstrap_and_reexec(
    args: argparse.Namespace,
    argv: list[str],
) -> tuple[int, dict[str, object]]:
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
        python, manifest, sentinel = _bootstrap_environment(repository, root)
        manifest_source = _read_bound(manifest, 64 * 1024 * 1024)
        environment = _base_environment()
        environment.update(
            {
                _SENTINEL: sentinel,
                _MANIFEST: str(manifest),
                _MANIFEST_DIGEST: hashlib.sha256(manifest_source).hexdigest(),
                "VIRTUAL_ENV": str(python.parent.parent),
            }
        )
        result = _run_bound_child(
            python,
            repository,
            environment,
            argv,
            sentinel,
        )
        return result
    finally:
        if root is not None and identity is not None:
            _cleanup_bootstrap_root(root, identity)


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    try:
        args = _parser().parse_args(args_list)
        if _child_binding(args):
            return _child_main(args)
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
