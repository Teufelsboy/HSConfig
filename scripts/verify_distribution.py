from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from email.message import Message
from email.parser import BytesParser, Parser
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


_BUILD_TOOLS = ("build", "setuptools", "wheel")
_CACHE_COMPONENTS = {
    ".hypothesis",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "__pycache__",
}
_FORBIDDEN_COMPONENTS = {
    ".superpowers": "superpowers",
    "output": "outputs",
    "outputs": "outputs",
    "test": "tests",
    "tests": "tests",
}
_RUNTIME_EVIDENCE_COMPONENTS = {
    ".codex-qa-round5",
    "hearthranger-logs",
    "hearthranger_logs",
    "hearthrangerlogs",
    "hearthstone-logs",
    "hearthstone_logs",
    "hearthstonelogs",
    "private-runtime",
    "private_runtime",
    "privateruntime",
    "runtime-evidence",
    "runtime_evidence",
    "runtime-exports",
    "runtime_exports",
    "runtimeexports",
}
_RUNTIME_EVIDENCE_FILENAMES = {
    "power.log",
    "hearthranger.log",
    "hearthstone.log",
}
_RUNTIME_EVIDENCE_COMPACT_MARKERS = {
    "hdtexport",
    "hdtreplay",
    "hearthrangerlogs",
    "hearthrangerlog",
    "hearthstonelogs",
    "hearthstonelog",
    "hsreplay",
    "powerlog",
    "privateruntime",
    "runtimeevidence",
    "runtimeexport",
    "runtimeexports",
}
_SDIST_ROOT_METADATA = {
    "LICENSE",
    "PKG-INFO",
    "README.md",
    "pyproject.toml",
    "setup.cfg",
}
_EGG_INFO_METADATA = {
    "PKG-INFO",
    "SOURCES.txt",
    "dependency_links.txt",
    "entry_points.txt",
    "requires.txt",
    "top_level.txt",
}
_DIST_INFO_METADATA = {
    "INSTALLER",
    "METADATA",
    "RECORD",
    "REQUESTED",
    "WHEEL",
    "direct_url.json",
    "entry_points.txt",
    "top_level.txt",
}
_PACKAGE_FILE_SUFFIXES = {".json", ".py", ".pyi"}
_LICENSE_EXPRESSION = "LicenseRef-Proprietary"
_LICENSE_FILENAME = "LICENSE"
_EXPECTED_LICENSE_SHA256 = (
    "0b256a96f1b55a1cb4c6f33739ea7222d0fce2fa266882383e964fa466b435e5"
)
_SDIST_FILENAME = re.compile(
    r"^hsconfig-(?P<version>[A-Za-z0-9][A-Za-z0-9.!+_]*)\.tar\.gz$",
    re.IGNORECASE,
)
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[/\\]")
_SSH_KEY_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])id_(?:dsa|ecdsa|ed25519|rsa)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_SECRET_TOKEN = re.compile(
    r"(?:^|[._-])(?:api[-_]?(?:key|token)|auth[-_]?(?:key|token)|"
    r"access[-_]?token|bearer[-_]?token|client[-_]?(?:key|secret|token)|"
    r"refresh[-_]?token|private[-_]?key|secret|secrets|credential|credentials|"
    r"password|passwd|token|tokens)(?:[._-]|$)",
    re.IGNORECASE,
)
_SECRET_COMPACT_FRAGMENTS = {
    "accesstoken",
    "apikey",
    "apitoken",
    "authtoken",
    "bearertoken",
    "clientsecret",
    "clienttoken",
    "privatekey",
    "refreshtoken",
}
_SAFE_TOKEN_FILENAMES = {"role_tokens.py"}
_SENSITIVE_EXTENSIONS = {".jks", ".key", ".keystore", ".p12", ".pem", ".pfx", ".ppk"}
# The pinned setuptools 83.0.0 backend emits Core Metadata 2.4 for both
# PKG-INFO files.
_SUPPORTED_CORE_METADATA_VERSIONS = frozenset({"2.4"})
_EXPECTED_SMOKE_PACKAGES = {
    "certifi",
    "charset-normalizer",
    "hearthstone",
    "hsconfig",
    "idna",
    "pip",
    "pyyaml",
    "requests",
    "urllib3",
}
_SKILL_BUNDLE_PACKAGE_PATH = "hsconfig/resources/codex_skill_bundle.json"
_SKILL_BUNDLE_SOURCE_PATH = Path("src") / _SKILL_BUNDLE_PACKAGE_PATH
_MAX_SKILL_BUNDLE_BYTES = 1_048_576


class DistributionVerificationError(RuntimeError):
    """Raised when isolated distribution verification cannot complete."""


class DistributionContentError(DistributionVerificationError):
    """Raised when an archive contains a forbidden or unexpected member."""


def _validate_license_payload(
    payload: bytes,
    *,
    label: str,
    error_type: type[DistributionVerificationError] = DistributionContentError,
) -> None:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise error_type(f"{label}_license_payload:invalid_utf8") from error
    if text.startswith("\ufeff"):
        raise error_type(f"{label}_license_payload:bom")
    if "\x00" in text:
        raise error_type(f"{label}_license_payload:nul")
    if re.search(r"\r(?!\n)", text):
        raise error_type(f"{label}_license_payload:bare_cr")
    canonical = text.replace("\r\n", "\n").encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != _EXPECTED_LICENSE_SHA256:
        raise error_type(f"{label}_license_payload:hash_mismatch")


@dataclass(frozen=True, slots=True)
class DistributionVerification:
    wheel: Path
    sdist: Path
    version: str
    wheel_smoke_passed: bool
    source_tree_clean: bool


def validate_distribution_members(kind: str, members: Iterable[str]) -> None:
    """Reject unsafe or non-runtime archive members."""
    if kind not in {"wheel", "sdist"}:
        raise ValueError(f"unsupported_distribution_kind:{kind}")
    canonical_names: set[str] = set()
    windows_names: dict[str, str] = {}
    for member in members:
        normalized = _record_archive_key(member, canonical_names, windows_names)
        _validate_safe_member_name(normalized)
        parts = PurePosixPath(normalized).parts
        _validate_forbidden_content(parts, normalized)
        allowed = (
            _wheel_member_allowed(parts)
            if kind == "wheel"
            else _sdist_member_allowed(parts)
        )
        if not allowed:
            raise DistributionContentError(
                f"forbidden_distribution_member:unexpected_{kind}_content:{member}"
            )


def validate_distribution_archive(kind: str, path: Path) -> None:
    """Validate archive metadata as well as every contained path."""
    if kind == "sdist":
        _validate_sdist_archive(path)
        return
    if kind == "wheel":
        _validate_wheel_archive(path)
        return
    raise ValueError(f"unsupported_distribution_kind:{kind}")


def _validate_safe_member_name(member: str) -> None:
    if member.startswith(("/", "//")) or _WINDOWS_ABSOLUTE.match(member):
        raise DistributionContentError(
            f"forbidden_distribution_member:absolute_path:{member}"
        )
    parts = PurePosixPath(member).parts
    if ".." in parts:
        raise DistributionContentError(
            f"forbidden_distribution_member:path_traversal:{member}"
        )
    for part in parts:
        if _secret_like_component(part):
            raise DistributionContentError(
                f"forbidden_distribution_member:secret_like_filename:{member}"
            )


def _canonical_extraction_key(member: str) -> tuple[str, str]:
    if member.startswith(("/", "//")) or _WINDOWS_ABSOLUTE.match(member):
        raise DistributionContentError(
            f"forbidden_distribution_member:absolute_path:{member}"
        )
    if not member or "\\" in member:
        raise DistributionContentError(
            f"forbidden_distribution_member:noncanonical_archive_path:{member}"
        )
    candidate = member[:-1] if member.endswith("/") else member
    raw_parts = candidate.split("/")
    if not candidate or any(part in {"", "."} for part in raw_parts):
        raise DistributionContentError(
            f"forbidden_distribution_member:noncanonical_archive_path:{member}"
        )
    if ".." in raw_parts:
        raise DistributionContentError(
            f"forbidden_distribution_member:path_traversal:{member}"
        )
    if any(part.rstrip(" .") != part or ":" in part for part in raw_parts):
        raise DistributionContentError(
            f"forbidden_distribution_member:noncanonical_archive_path:{member}"
        )
    canonical = "/".join(raw_parts)
    return canonical, "/".join(part.casefold() for part in raw_parts)


def _secret_like_component(component: str) -> bool:
    lowered = component.casefold()
    if lowered in _SAFE_TOKEN_FILENAMES:
        return False
    dot_parts = lowered.split(".")
    base_name = dot_parts[0]
    suffix_chain = {f".{part}" for part in dot_parts[1:] if part}
    compact = re.sub(r"[^a-z0-9]", "", lowered)
    return (
        lowered == ".env"
        or lowered.startswith(".env.")
        or _SSH_KEY_TOKEN.search(lowered) is not None
        or base_name in {"id_dsa", "id_ecdsa", "id_ed25519", "id_rsa"}
        or bool(suffix_chain.intersection(_SENSITIVE_EXTENSIONS))
        or _SECRET_TOKEN.search(lowered) is not None
        or any(fragment in compact for fragment in _SECRET_COMPACT_FRAGMENTS)
    )


def _validate_forbidden_content(parts: Sequence[str], member: str) -> None:
    lowered_parts = tuple(part.lower() for part in parts)
    for part in lowered_parts:
        reason = _FORBIDDEN_COMPONENTS.get(part)
        if reason is not None:
            raise DistributionContentError(
                f"forbidden_distribution_member:{reason}:{member}"
            )
        if part in _CACHE_COMPONENTS:
            raise DistributionContentError(
                f"forbidden_distribution_member:local_cache:{member}"
            )
        if part in _RUNTIME_EVIDENCE_COMPONENTS:
            raise DistributionContentError(
                f"forbidden_distribution_member:runtime_evidence:{member}"
            )
        compact_basename = re.sub(r"[^a-z0-9]", "", part)
        if any(
            marker in compact_basename for marker in _RUNTIME_EVIDENCE_COMPACT_MARKERS
        ):
            raise DistributionContentError(
                f"forbidden_distribution_member:runtime_evidence:{member}"
            )
        tokens = set(re.findall(r"[a-z0-9]+", part))
        log_tokens = {"log", "logs"}
        if (
            ("power" in tokens and bool(tokens.intersection(log_tokens)))
            or ("hearthranger" in tokens and bool(tokens.intersection(log_tokens)))
            or ("hearthstone" in tokens and bool(tokens.intersection(log_tokens)))
            or (
                "runtime" in tokens
                and bool(tokens.intersection({"evidence", "export", "exports"}))
            )
            or {"private", "runtime"}.issubset(tokens)
        ):
            raise DistributionContentError(
                f"forbidden_distribution_member:runtime_evidence:{member}"
            )
        if "hdt" in compact_basename and "xml" in compact_basename:
            raise DistributionContentError(
                f"forbidden_distribution_member:runtime_evidence:{member}"
            )
    name = lowered_parts[-1] if lowered_parts else ""
    if name == "conftest.py" or name.startswith("test_") or name.endswith("_test.py"):
        raise DistributionContentError(f"forbidden_distribution_member:tests:{member}")
    if name in _RUNTIME_EVIDENCE_FILENAMES or name.endswith(
        (".hdtreplay", ".hsreplay")
    ):
        raise DistributionContentError(
            f"forbidden_distribution_member:runtime_evidence:{member}"
        )


def _wheel_member_allowed(parts: Sequence[str]) -> bool:
    if len(parts) < 2:
        return False
    root = parts[0]
    if root == "hsconfig":
        name = parts[-1]
        return name == "py.typed" or Path(name).suffix.lower() in _PACKAGE_FILE_SUFFIXES
    if not root.startswith("hsconfig-") or not root.endswith(".dist-info"):
        return False
    if len(parts) == 2:
        return parts[-1] in _DIST_INFO_METADATA
    return (
        len(parts) == 3
        and parts[1] == "licenses"
        and parts[2] == _LICENSE_FILENAME
    )


def _sdist_member_allowed(parts: Sequence[str]) -> bool:
    if len(parts) < 2 or not parts[0].startswith("hsconfig-"):
        return False
    relative = parts[1:]
    if len(relative) == 1:
        return relative[0] in _SDIST_ROOT_METADATA
    if relative[:2] == ("src", "hsconfig"):
        name = relative[-1]
        return name == "py.typed" or Path(name).suffix.lower() in _PACKAGE_FILE_SUFFIXES
    if len(relative) == 3 and relative[:2] == ("src", "hsconfig.egg-info"):
        return relative[-1] in _EGG_INFO_METADATA
    return False


def _wheel_directory_allowed(parts: Sequence[str]) -> bool:
    if not parts:
        return False
    root = parts[0]
    if root == "hsconfig":
        return True
    return (
        root.startswith("hsconfig-")
        and root.endswith(".dist-info")
        and (len(parts) == 1 or (len(parts) == 2 and parts[1] == "licenses"))
    )


def _sdist_directory_allowed(parts: Sequence[str]) -> bool:
    if not parts or not parts[0].startswith("hsconfig-"):
        return False
    relative = parts[1:]
    return (
        not relative
        or relative == ("src",)
        or relative[:2] == ("src", "hsconfig")
        or relative == ("src", "hsconfig.egg-info")
    )


def _validate_archive_path(kind: str, member: str, *, directory: bool) -> None:
    normalized, _windows_key = _canonical_extraction_key(member)
    _validate_safe_member_name(normalized)
    parts = PurePosixPath(normalized).parts
    _validate_forbidden_content(parts, normalized)
    if directory:
        allowed = (
            _wheel_directory_allowed(parts)
            if kind == "wheel"
            else _sdist_directory_allowed(parts)
        )
    else:
        allowed = (
            _wheel_member_allowed(parts)
            if kind == "wheel"
            else _sdist_member_allowed(parts)
        )
    if not allowed:
        raise DistributionContentError(
            f"forbidden_distribution_member:unexpected_{kind}_content:{member}"
        )


def _validate_link_target(target: str) -> None:
    normalized, _windows_key = _canonical_extraction_key(target)
    _validate_safe_member_name(normalized)
    _validate_forbidden_content(PurePosixPath(normalized).parts, normalized)


def _archive_identity(kind: str, path: Path) -> tuple[str, str]:
    if kind == "sdist":
        match = _SDIST_FILENAME.fullmatch(path.name)
        if match is None:
            raise DistributionContentError(f"invalid_sdist_filename:{path.name}")
        return "hsconfig", match.group("version")
    if not path.name.endswith(".whl"):
        raise DistributionContentError(f"invalid_wheel_filename:{path.name}")
    parts = path.name[:-4].split("-")
    if len(parts) not in {5, 6}:
        raise DistributionContentError(f"invalid_wheel_filename:{path.name}")
    distribution_name, version = parts[:2]
    if distribution_name.replace("_", "-").casefold() != "hsconfig":
        raise DistributionContentError(
            f"artifact_distribution_mismatch:{distribution_name}"
        )
    return "hsconfig", version


def _record_archive_key(
    member: str,
    canonical_names: set[str],
    windows_names: dict[str, str],
) -> str:
    canonical, windows_key = _canonical_extraction_key(member)
    if canonical in canonical_names:
        raise DistributionContentError(f"duplicate_archive_member:{member}")
    previous = windows_names.get(windows_key)
    if previous is not None and previous != canonical:
        raise DistributionContentError(
            f"windows_casefold_collision:{previous}:{canonical}"
        )
    canonical_names.add(canonical)
    windows_names[windows_key] = canonical
    return canonical


def _validate_sdist_archive(path: Path) -> None:
    distribution_name, version = _archive_identity("sdist", path)
    expected_root = f"{distribution_name}-{version}"
    names: set[str] = set()
    regular_files: set[str] = set()
    directories: set[str] = set()
    windows_names: dict[str, str] = {}
    roots: set[str] = set()
    root_pkg_info_path = f"{expected_root}/PKG-INFO"
    egg_pkg_info_path = f"{expected_root}/src/hsconfig.egg-info/PKG-INFO"
    license_path = f"{expected_root}/{_LICENSE_FILENAME}"
    pkg_info_payloads: dict[str, bytes] = {}
    license_payload: bytes | None = None
    with tarfile.open(path, "r:gz") as archive:
        for entry in archive.getmembers():
            normalized = _record_archive_key(entry.name, names, windows_names)
            roots.add(normalized.split("/", 1)[0])
            _validate_archive_path("sdist", entry.name, directory=entry.isdir())
            if entry.issym() or entry.islnk():
                _validate_link_target(entry.linkname)
            if not (entry.isfile() or entry.isdir()):
                raise DistributionContentError(
                    f"non_regular_tar_entry:{entry.name}:type={entry.type!r}"
                )
            if entry.isfile():
                regular_files.add(normalized)
                if normalized in {root_pkg_info_path, egg_pkg_info_path}:
                    pkg_info_payloads[normalized] = _read_tar_metadata(archive, entry)
                if normalized == license_path:
                    license_payload = _read_tar_metadata(archive, entry)
            else:
                directories.add(normalized)
    if regular_files.intersection(directories):
        raise DistributionContentError("conflicting_sdist_member_types")
    if roots != {expected_root}:
        raise DistributionContentError(
            f"archive_root_mismatch:expected={expected_root}:actual={sorted(roots)}"
        )
    required_members = {
        f"{expected_root}/PKG-INFO",
        f"{expected_root}/LICENSE",
        f"{expected_root}/README.md",
        f"{expected_root}/pyproject.toml",
        f"{expected_root}/src/hsconfig/__init__.py",
        *(
            f"{expected_root}/src/hsconfig.egg-info/{metadata}"
            for metadata in _EGG_INFO_METADATA
        ),
    }
    missing = sorted(required_members - regular_files)
    if missing:
        raise DistributionContentError("incomplete_sdist:missing=" + ",".join(missing))
    if license_payload is None:
        raise DistributionContentError("incomplete_sdist:missing=" + license_path)
    _validate_license_payload(license_payload, label="sdist")
    root_metadata = _validate_pkg_info(
        pkg_info_payloads[root_pkg_info_path],
        label="root",
        expected_version=version,
    )
    egg_metadata = _validate_pkg_info(
        pkg_info_payloads[egg_pkg_info_path],
        label="egg_info",
        expected_version=version,
    )
    _validate_license_metadata(root_metadata, label="root")
    _validate_license_metadata(egg_metadata, label="egg_info")


def _read_tar_metadata(archive: tarfile.TarFile, entry: tarfile.TarInfo) -> bytes:
    extracted = archive.extractfile(entry)
    if extracted is None:
        raise DistributionContentError(f"invalid_pkg_info:unreadable:{entry.name}")
    payload = extracted.read(1_048_577)
    if len(payload) > 1_048_576:
        raise DistributionContentError(f"invalid_pkg_info:too_large:{entry.name}")
    return payload


def _parse_metadata(payload: bytes, *, label: str) -> Message:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DistributionContentError(
            f"invalid_pkg_info:{label}:invalid_utf8"
        ) from error
    if text.startswith("\ufeff"):
        raise DistributionContentError(f"invalid_pkg_info:{label}:bom")
    if "\x00" in text:
        raise DistributionContentError(f"invalid_pkg_info:{label}:nul")
    if re.search(r"\r(?!\n)", text):
        raise DistributionContentError(f"invalid_pkg_info:{label}:bare_cr")
    try:
        metadata = BytesParser().parsebytes(payload)
    except (TypeError, ValueError) as error:
        raise DistributionContentError(f"invalid_pkg_info:{label}") from error
    if metadata.defects:
        raise DistributionContentError(f"invalid_pkg_info:{label}")
    return metadata


def _validate_pkg_info(
    payload: bytes,
    *,
    label: str,
    expected_version: str,
) -> Message:
    metadata = _parse_metadata(payload, label=label)
    metadata_versions = metadata.get_all("Metadata-Version", [])
    names = metadata.get_all("Name", [])
    versions = metadata.get_all("Version", [])
    if len(metadata_versions) != 1 or len(names) != 1 or len(versions) != 1:
        raise DistributionContentError(f"invalid_pkg_info:{label}")
    metadata_version = metadata_versions[0].strip()
    if metadata_version not in _SUPPORTED_CORE_METADATA_VERSIONS:
        raise DistributionContentError(
            f"invalid_metadata_version:{label}:actual={metadata_version}"
        )
    if _normalize_package_name(names[0]) != "hsconfig":
        raise DistributionContentError(
            f"pkg_info_name_mismatch:{label}:actual={names[0]}"
        )
    if versions[0] != expected_version:
        raise DistributionContentError(
            "pkg_info_version_mismatch:"
            f"{label}:expected={expected_version}:actual={versions[0]}"
        )
    return metadata


def _validate_wheel_archive(path: Path) -> None:
    distribution_name, version = _archive_identity("wheel", path)
    expected_dist_info = f"{distribution_name}-{version}.dist-info"
    names: set[str] = set()
    windows_names: dict[str, str] = {}
    dist_info_roots: set[str] = set()
    regular_files: set[str] = set()
    metadata_path = f"{expected_dist_info}/METADATA"
    license_path = f"{expected_dist_info}/licenses/{_LICENSE_FILENAME}"
    contract_payloads: dict[str, bytes] = {}
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            normalized = _record_archive_key(entry.filename, names, windows_names)
            root = normalized.split("/", 1)[0]
            if root.endswith(".dist-info"):
                dist_info_roots.add(root)
            mode = (entry.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(mode)
            is_directory = entry.is_dir() or file_type == stat.S_IFDIR
            _validate_archive_path("wheel", entry.filename, directory=is_directory)
            if file_type == stat.S_IFLNK:
                try:
                    target = archive.read(entry).decode("utf-8")
                except UnicodeDecodeError as error:
                    raise DistributionContentError(
                        f"invalid_zip_link_target:{entry.filename}"
                    ) from error
                _validate_link_target(target)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise DistributionContentError(
                    f"non_regular_zip_entry:{entry.filename}:mode={mode:o}"
                )
            if not is_directory:
                regular_files.add(normalized)
                if normalized in {metadata_path, license_path}:
                    contract_payloads[normalized] = _read_zip_payload(archive, entry)
    if dist_info_roots != {expected_dist_info}:
        raise DistributionContentError(
            "archive_root_mismatch:"
            f"expected={expected_dist_info}:actual={sorted(dist_info_roots)}"
        )
    required_members = {metadata_path, license_path}
    missing = sorted(required_members - regular_files)
    if missing:
        raise DistributionContentError("incomplete_wheel:missing=" + ",".join(missing))
    metadata = _validate_pkg_info(
        contract_payloads[metadata_path],
        label="wheel",
        expected_version=version,
    )
    _validate_license_metadata(metadata, label="wheel")
    _validate_license_payload(contract_payloads[license_path], label="wheel")


def _read_zip_payload(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> bytes:
    with archive.open(entry) as source:
        payload = source.read(1_048_577)
    if len(payload) > 1_048_576:
        raise DistributionContentError(f"invalid_wheel_payload:too_large:{entry.filename}")
    return payload


def _validate_license_metadata(metadata: Message, *, label: str) -> None:
    expressions = metadata.get_all("License-Expression", [])
    license_files = metadata.get_all("License-File", [])
    if expressions != [_LICENSE_EXPRESSION]:
        raise DistributionContentError(
            f"{label}_license_expression:actual=" + repr(expressions)
        )
    if license_files != [_LICENSE_FILENAME]:
        raise DistributionContentError(
            f"{label}_license_file:actual=" + repr(license_files)
        )


def _select_distribution_archives(output_root: Path) -> tuple[Path, Path]:
    wheels = sorted(output_root.glob("*.whl"))
    sdists = sorted(output_root.glob("*.tar.gz"))
    if len(wheels) != 1:
        raise DistributionContentError(f"wheel_count:{len(wheels)}")
    if len(sdists) != 1:
        raise DistributionContentError(f"sdist_count:{len(sdists)}")
    return wheels[0], sdists[0]


def _assert_skill_bundle_parity(
    source_root: Path,
    wheel: Path,
    sdist: Path,
) -> tuple[str, str]:
    """Require exact validated skill-resource bytes in source, sdist, and wheel."""
    source_path = source_root / _SKILL_BUNDLE_SOURCE_PATH
    try:
        source_payload = source_path.read_bytes()
    except OSError as error:
        raise DistributionContentError(
            "skill_bundle_source_unreadable"
        ) from error
    if len(source_payload) > _MAX_SKILL_BUNDLE_BYTES:
        raise DistributionContentError("skill_bundle_source_oversize")

    with zipfile.ZipFile(wheel) as archive:
        wheel_rows = [
            entry
            for entry in archive.infolist()
            if entry.filename == _SKILL_BUNDLE_PACKAGE_PATH
        ]
        if len(wheel_rows) != 1 or wheel_rows[0].is_dir():
            raise DistributionContentError("skill_bundle_wheel_member_count")
        wheel_payload = _read_zip_payload(archive, wheel_rows[0])

    _sdist_name, sdist_version = _archive_identity("sdist", sdist)
    sdist_member = (
        f"hsconfig-{sdist_version}/src/{_SKILL_BUNDLE_PACKAGE_PATH}"
    )
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_rows = [
            entry for entry in archive.getmembers() if entry.name == sdist_member
        ]
        if len(sdist_rows) != 1 or not sdist_rows[0].isreg():
            raise DistributionContentError("skill_bundle_sdist_member_count")
        sdist_payload = _read_tar_metadata(archive, sdist_rows[0])

    if source_payload != sdist_payload or source_payload != wheel_payload:
        raise DistributionContentError("skill_bundle_artifact_parity_mismatch")
    try:
        from hsconfig.external_skill_bundle import (
            compute_bundle_aggregate,
            decode_skill_bundle,
        )

        files = decode_skill_bundle(source_payload)
    except (ImportError, ValueError, TypeError) as error:
        raise DistributionContentError("skill_bundle_payload_invalid") from error
    return (
        hashlib.sha256(source_payload).hexdigest(),
        compute_bundle_aggregate(files),
    )


def verify_distribution(repo_root: Path | None = None) -> DistributionVerification:
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    constraints = root / "constraints-ci.txt"
    before = _git_status(root)
    temporary_root: Path | None = None
    result: DistributionVerification | None = None
    primary_error: BaseException | None = None
    try:
        locked = _locked_versions(constraints)
        missing = sorted({"pip", *_BUILD_TOOLS} - locked.keys())
        if missing:
            raise DistributionVerificationError(
                "locked_build_tools_missing:" + ",".join(missing)
            )
        with tempfile.TemporaryDirectory(prefix="hsconfig-distribution-") as temporary:
            temporary_root = Path(temporary)
            result = _verify_distribution_in_temporary(
                root,
                constraints,
                locked,
                temporary_root,
            )
    except BaseException as error:
        primary_error = error

    post_errors: list[str] = []
    try:
        after = _git_status(root)
        if after != before:
            post_errors.append("source_worktree_status_changed")
    except BaseException as error:
        post_errors.append(f"source_worktree_status_unavailable:{error}")
    if temporary_root is not None and temporary_root.exists():
        post_errors.append(f"temporary_residue:{temporary_root}")
    if post_errors:
        detail = ":".join(post_errors)
        if primary_error is not None:
            detail += f":primary={primary_error}"
        raise DistributionVerificationError(
            f"post_verification_gate_failed:{detail}"
        ) from primary_error
    if primary_error is not None:
        raise primary_error
    if result is None:
        raise DistributionVerificationError("verification_result_missing")
    return result


def _verify_distribution_in_temporary(
    root: Path,
    constraints: Path,
    locked: dict[str, str],
    temporary_root: Path,
) -> DistributionVerification:
    source_root = temporary_root / "source"
    output_root = temporary_root / "dist"
    build_venv = temporary_root / "build-venv"
    smoke_venv = temporary_root / "smoke-venv"
    _stage_build_source(root, source_root)
    _create_venv(build_venv)
    build_python = _venv_python(build_venv)
    _install_locked_pip(build_python, constraints, locked["pip"])
    _run(
        [
            str(build_python),
            "-m",
            "pip",
            "--isolated",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--constraint",
            str(constraints),
            *(f"{name}=={locked[name]}" for name in _BUILD_TOOLS),
        ],
        cwd=temporary_root,
    )
    output_root.mkdir()
    _run(
        [
            str(build_python),
            "-m",
            "build",
            "--no-isolation",
            "--sdist",
            "--wheel",
            "--outdir",
            str(output_root),
            str(source_root),
        ],
        cwd=temporary_root,
    )
    wheel, sdist = _select_distribution_archives(output_root)
    validate_distribution_archive("wheel", wheel)
    validate_distribution_archive("sdist", sdist)
    skill_bundle_sha256, skill_bundle_aggregate_sha256 = _assert_skill_bundle_parity(
        source_root,
        wheel,
        sdist,
    )
    version = _wheel_version(wheel)

    _create_venv(smoke_venv)
    smoke_python = _venv_python(smoke_venv)
    _install_locked_pip(smoke_python, constraints, locked["pip"])
    _run(
        [
            str(smoke_python),
            "-m",
            "pip",
            "--isolated",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--constraint",
            str(constraints),
            str(wheel),
        ],
        cwd=temporary_root,
    )
    _run(
        [str(smoke_python), "-m", "pip", "--isolated", "uninstall", "-y", "setuptools"],
        cwd=temporary_root,
    )
    inventory_result = _run(
        [str(smoke_python), "-m", "pip", "--isolated", "list", "--format=json"],
        cwd=temporary_root,
    )
    _assert_smoke_inventory(json.loads(inventory_result.stdout))
    module_result = _run(
        [
            str(smoke_python),
            "-c",
            "import pathlib, hsconfig; print(pathlib.Path(hsconfig.__file__).resolve())",
        ],
        cwd=temporary_root,
    )
    _assert_installed_module_path(
        Path(module_result.stdout.strip()),
        smoke_venv,
    )
    resource_result = _run(
        [
            str(smoke_python),
            "-c",
            (
                "import hashlib, importlib.resources, json; "
                "from hsconfig.external_skill_bundle import "
                "compute_bundle_aggregate, load_embedded_skill_bundle; "
                "payload = importlib.resources.files('hsconfig').joinpath("
                "'resources', 'codex_skill_bundle.json').read_bytes(); "
                "files = load_embedded_skill_bundle(); "
                "print(json.dumps({'aggregate_sha256': "
                "compute_bundle_aggregate(files), 'file_count': len(files), "
                "'resource_sha256': hashlib.sha256(payload).hexdigest()}, "
                "sort_keys=True))"
            ),
        ],
        cwd=temporary_root,
    )
    try:
        installed_resource = json.loads(resource_result.stdout)
    except json.JSONDecodeError as error:
        raise DistributionVerificationError(
            "installed_skill_bundle_resource_invalid"
        ) from error
    if (
        not isinstance(installed_resource, dict)
        or set(installed_resource)
        != {"aggregate_sha256", "file_count", "resource_sha256"}
        or installed_resource["file_count"] != 9
        or installed_resource["resource_sha256"] != skill_bundle_sha256
        or installed_resource["aggregate_sha256"]
        != skill_bundle_aggregate_sha256
    ):
        raise DistributionVerificationError(
            "installed_skill_bundle_resource_mismatch"
        )
    hsconfig = _venv_executable(smoke_venv, "hsconfig")
    version_result = _run([str(hsconfig), "--version"], cwd=temporary_root)
    if version_result.stdout.strip() != f"hsconfig {version}":
        raise DistributionVerificationError(
            "installed_version_mismatch:"
            f"expected=hsconfig {version}:actual={version_result.stdout.strip()}"
        )
    help_result = _run([str(hsconfig), "--help"], cwd=temporary_root)
    if "usage: hsconfig" not in help_result.stdout:
        raise DistributionVerificationError("installed_help_missing_usage")
    sentinel_result = _run(
        [str(hsconfig), "contract-spine-sentinel", "--json"],
        cwd=temporary_root,
        allowed_returncodes=(1,),
    )
    sentinel = _decode_sentinel_json(sentinel_result.stdout)
    _assert_isolated_sentinel_result(sentinel, sentinel_result.returncode)
    supported_result = _run(
        [
            str(hsconfig),
            "contract-spine-sentinel",
            "--repo-root",
            str(source_root),
            "--json",
        ],
        cwd=temporary_root,
    )
    supported = _decode_sentinel_json(supported_result.stdout)
    _assert_supported_sentinel_result(supported)
    return DistributionVerification(
        wheel=Path(wheel.name),
        sdist=Path(sdist.name),
        version=version,
        wheel_smoke_passed=True,
        source_tree_clean=True,
    )


def _stage_build_source(repo_root: Path, destination: Path) -> None:
    _assert_safe_source_input(repo_root / "pyproject.toml", expected="file")
    _assert_safe_source_input(repo_root / "README.md", expected="file")
    _assert_safe_source_input(repo_root / "LICENSE", expected="file")
    try:
        source_license_payload = (repo_root / "LICENSE").read_bytes()
    except OSError as error:
        raise DistributionVerificationError(
            "source_license_payload:unreadable"
        ) from error
    _validate_license_payload(
        source_license_payload,
        label="source",
        error_type=DistributionVerificationError,
    )
    _assert_safe_source_tree(repo_root / "src")
    destination.mkdir()
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy2(
            repo_root / name,
            destination / name,
            follow_symlinks=False,
        )
    shutil.copytree(
        repo_root / "src",
        destination / "src",
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    _assert_safe_source_input(destination / "pyproject.toml", expected="file")
    _assert_safe_source_input(destination / "README.md", expected="file")
    _assert_safe_source_input(destination / "LICENSE", expected="file")
    try:
        staged_license_payload = (destination / "LICENSE").read_bytes()
    except OSError as error:
        raise DistributionVerificationError(
            "staged_license_payload:unreadable"
        ) from error
    _validate_license_payload(
        staged_license_payload,
        label="staged",
        error_type=DistributionVerificationError,
    )
    _assert_safe_source_tree(destination / "src")


def _is_reparse_point(file_stat: os.stat_result) -> bool:
    attributes = getattr(file_stat, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _assert_safe_source_input(path: Path, *, expected: str) -> os.stat_result:
    try:
        file_stat = path.lstat()
    except OSError as error:
        raise DistributionVerificationError(
            f"unsafe_source_input:unavailable:{path}:{error}"
        ) from error
    unsafe_link = stat.S_ISLNK(file_stat.st_mode) or _is_reparse_point(file_stat)
    expected_type = (
        stat.S_ISREG(file_stat.st_mode)
        if expected == "file"
        else stat.S_ISDIR(file_stat.st_mode)
    )
    if unsafe_link or not expected_type:
        raise DistributionVerificationError(
            f"unsafe_source_input:{expected}_required:{path}"
        )
    return file_stat


def _assert_safe_source_tree(root: Path) -> None:
    _assert_safe_source_input(root, expected="directory")
    try:
        entries = list(os.scandir(root))
    except OSError as error:
        raise DistributionVerificationError(
            f"unsafe_source_input:unreadable_directory:{root}:{error}"
        ) from error
    for entry in entries:
        path = Path(entry.path)
        try:
            file_stat = entry.stat(follow_symlinks=False)
        except OSError as error:
            raise DistributionVerificationError(
                f"unsafe_source_input:unavailable:{path}:{error}"
            ) from error
        if stat.S_ISLNK(file_stat.st_mode) or _is_reparse_point(file_stat):
            raise DistributionVerificationError(f"unsafe_source_input:link:{path}")
        if stat.S_ISDIR(file_stat.st_mode):
            _assert_safe_source_tree(path)
        elif not stat.S_ISREG(file_stat.st_mode):
            raise DistributionVerificationError(
                f"unsafe_source_input:non_regular:{path}"
            )


def _locked_versions(path: Path) -> dict[str, str]:
    locked: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        locked[re.sub(r"[-_.]+", "-", name).lower()] = version
    return locked


def _install_locked_pip(python: Path, constraints: Path, version: str) -> None:
    _run(
        [
            str(python),
            "-m",
            "pip",
            "--isolated",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--constraint",
            str(constraints),
            f"pip=={version}",
        ],
        cwd=constraints.parent,
    )


def _create_venv(path: Path) -> None:
    _run([sys.executable, "-m", "venv", str(path)], cwd=path.parent)


def _venv_python(venv: Path) -> Path:
    return _venv_executable(venv, "python")


def _venv_executable(venv: Path, name: str) -> Path:
    if os.name == "nt":
        executable = venv / "Scripts" / f"{name}.exe"
    else:
        executable = venv / "bin" / name
    if not executable.is_file():
        raise DistributionVerificationError(f"venv_executable_missing:{name}")
    return executable


def _wheel_version(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        metadata = [
            name
            for name in archive.namelist()
            if name.startswith("hsconfig-") and name.endswith(".dist-info/METADATA")
        ]
        if len(metadata) != 1:
            raise DistributionContentError(f"wheel_metadata_count:{len(metadata)}")
        parsed = Parser().parsestr(archive.read(metadata[0]).decode("utf-8"))
    version = parsed.get("Version")
    if not version:
        raise DistributionContentError("wheel_version_missing")
    return version


def _assert_installed_module_path(module_path: Path, smoke_venv: Path) -> None:
    module = module_path.resolve()
    venv = smoke_venv.resolve()
    try:
        relative = module.relative_to(venv)
    except ValueError as error:
        raise DistributionVerificationError(
            f"installed_module_outside_smoke_venv:{module}"
        ) from error
    if "site-packages" not in {part.casefold() for part in relative.parts}:
        raise DistributionVerificationError(
            f"installed_module_not_in_site_packages:{module}"
        )


def _decode_sentinel_json(raw: str) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        payload: dict[str, object] = {}
        for key, value in pairs:
            if key in payload:
                raise DistributionVerificationError(
                    "installed_contract_spine_json_invalid"
                )
            payload[key] = value
        return payload

    def reject_nonstandard_constant(_constant: str) -> object:
        raise DistributionVerificationError("installed_contract_spine_json_invalid")

    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_nonstandard_constant,
        )
    except DistributionVerificationError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise DistributionVerificationError(
            "installed_contract_spine_json_invalid"
        ) from error


def _assert_isolated_sentinel_result(payload: object, returncode: int) -> None:
    expected = {
        "status": "failed",
        "errors": [
            "contract-spine-sentinel --repo-root must be an HSConfig repository root"
        ],
    }
    if returncode != 1 or payload != expected:
        raise DistributionVerificationError(
            "installed_contract_spine_isolation_invalid"
        )


def _assert_supported_sentinel_result(payload: object) -> None:
    expected_keys = {
        "schema_version",
        "status",
        "authority",
        "operator_gate_impact",
        "apply_blocking",
        "checks",
        "contract_invariants",
        "problems",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise DistributionVerificationError(
            "installed_contract_spine_supported_interface_invalid"
        )
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise DistributionVerificationError(
            "installed_contract_spine_supported_interface_invalid"
        )
    if payload.get("status") != "clean":
        raise DistributionVerificationError(
            "installed_contract_spine_supported_interface_not_clean:"
            f"status={payload.get('status')}"
        )
    if not (
        payload.get("authority") == "diagnostic_only"
        and payload.get("operator_gate_impact") == "diagnostic_only"
        and payload.get("apply_blocking") is False
        and isinstance(payload.get("checks"), Mapping)
        and isinstance(payload.get("contract_invariants"), Mapping)
        and type(payload.get("problems")) is list
        and payload.get("problems") == []
    ):
        raise DistributionVerificationError(
            "installed_contract_spine_supported_interface_invalid"
        )


def _normalize_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _assert_smoke_inventory(packages: object) -> None:
    if not isinstance(packages, list):
        raise DistributionVerificationError("invalid_smoke_inventory")
    actual: set[str] = set()
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("name"), str):
            raise DistributionVerificationError("invalid_smoke_inventory_entry")
        actual.add(_normalize_package_name(package["name"]))
    unexpected = sorted(actual - _EXPECTED_SMOKE_PACKAGES)
    missing = sorted(_EXPECTED_SMOKE_PACKAGES - actual)
    if unexpected:
        raise DistributionVerificationError(
            "unexpected_package:" + ",".join(unexpected)
        )
    if missing:
        raise DistributionVerificationError("missing_package:" + ",".join(missing))


def _git_status(root: Path) -> str:
    return _run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
    ).stdout


def _controlled_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in tuple(environment):
        upper = key.upper()
        if upper in {"PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX"}:
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
        }
    )
    return environment


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    allowed_returncodes: Sequence[int] = (0,),
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=_controlled_environment(),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode not in allowed_returncodes:
        rendered = subprocess.list2cmdline(list(command))
        stderr_tail = result.stderr[-2000:].strip()
        stdout_tail = result.stdout[-2000:].strip()
        raise DistributionVerificationError(
            f"command_failed:{result.returncode}:{rendered}:"
            f"stdout={stdout_tail}:stderr={stderr_tail}"
        )
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and smoke-test clean HSConfig wheel and sdist artifacts."
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = verify_distribution()
    except (
        DistributionVerificationError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        payload = {"status": "failed", "errors": [str(error)]}
        print(json.dumps(payload, sort_keys=True) if args.json else str(error))
        return 1
    payload = {"status": "passed", **asdict(result)}
    payload["wheel"] = str(payload["wheel"])
    payload["sdist"] = str(payload["sdist"])
    print(json.dumps(payload, sort_keys=True) if args.json else payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
