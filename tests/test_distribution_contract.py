from __future__ import annotations

import io
import json
import os
import stat
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import verify_distribution as distribution
from scripts.verify_distribution import (
    DistributionContentError,
    DistributionVerificationError,
    _assert_installed_module_path,
    _assert_supported_sentinel_result,
    _assert_smoke_inventory,
    _run,
    _select_distribution_archives,
    _stage_build_source,
    validate_distribution_archive,
    validate_distribution_members,
)


_VALID_PKG_INFO = b"Metadata-Version: 2.4\nName: hsconfig\nVersion: 1.0.0\n"
_EGG_INFO_FILES = (
    "PKG-INFO",
    "SOURCES.txt",
    "dependency_links.txt",
    "entry_points.txt",
    "requires.txt",
    "top_level.txt",
)


def _add_tar_file(archive: tarfile.TarFile, name: str, payload: bytes = b"") -> None:
    entry = tarfile.TarInfo(name)
    entry.size = len(payload)
    archive.addfile(entry, io.BytesIO(payload))


def _write_complete_sdist(
    path: Path,
    *,
    root_pkg_info: bytes = _VALID_PKG_INFO,
    egg_pkg_info: bytes = _VALID_PKG_INFO,
    init_as_directory: bool = False,
    extra_files: tuple[str, ...] = (),
) -> None:
    root = "hsconfig-1.0.0"
    with tarfile.open(path, "w:gz") as archive:
        _add_tar_file(archive, f"{root}/PKG-INFO", root_pkg_info)
        _add_tar_file(archive, f"{root}/README.md", b"# HSConfig\n")
        _add_tar_file(
            archive, f"{root}/pyproject.toml", b"[project]\nname='hsconfig'\n"
        )
        init_path = f"{root}/src/hsconfig/__init__.py"
        if init_as_directory:
            entry = tarfile.TarInfo(init_path)
            entry.type = tarfile.DIRTYPE
            archive.addfile(entry)
        else:
            _add_tar_file(archive, init_path, b"__version__ = '1.0.0'\n")
        for filename in _EGG_INFO_FILES:
            payload = egg_pkg_info if filename == "PKG-INFO" else b"\n"
            _add_tar_file(
                archive,
                f"{root}/src/hsconfig.egg-info/{filename}",
                payload,
            )
        for relative in extra_files:
            _add_tar_file(archive, f"{root}/{relative}", b"concealed")


def test_distribution_members_allow_only_runtime_package_and_standard_metadata() -> (
    None
):
    wheel_members = [
        "hsconfig/__init__.py",
        "hsconfig/cli.py",
        "hsconfig/policies/default_policy.json",
        "hsconfig/resources/card_metadata.json",
        "hsconfig-1.0.0.dist-info/METADATA",
        "hsconfig-1.0.0.dist-info/WHEEL",
        "hsconfig-1.0.0.dist-info/entry_points.txt",
        "hsconfig-1.0.0.dist-info/top_level.txt",
        "hsconfig-1.0.0.dist-info/RECORD",
    ]
    sdist_members = [
        "hsconfig-1.0.0/PKG-INFO",
        "hsconfig-1.0.0/README.md",
        "hsconfig-1.0.0/pyproject.toml",
        "hsconfig-1.0.0/src/hsconfig/__init__.py",
        "hsconfig-1.0.0/src/hsconfig/policies/default_policy.json",
        "hsconfig-1.0.0/src/hsconfig/resources/card_metadata.json",
        "hsconfig-1.0.0/src/hsconfig.egg-info/PKG-INFO",
        "hsconfig-1.0.0/src/hsconfig.egg-info/SOURCES.txt",
        "hsconfig-1.0.0/src/hsconfig.egg-info/dependency_links.txt",
        "hsconfig-1.0.0/src/hsconfig.egg-info/entry_points.txt",
        "hsconfig-1.0.0/src/hsconfig.egg-info/requires.txt",
        "hsconfig-1.0.0/src/hsconfig.egg-info/top_level.txt",
    ]

    validate_distribution_members("wheel", wheel_members)
    validate_distribution_members("sdist", sdist_members)


def test_distribution_member_matrix_rejects_casefold_collisions() -> None:
    with pytest.raises(DistributionContentError, match="windows_casefold_collision"):
        validate_distribution_members(
            "wheel",
            ["hsconfig/cli.py", "HSCONFIG/CLI.py"],
        )


@pytest.mark.parametrize(
    ("member", "reason"),
    [
        ("hsconfig-1.0.0/tests/test_cli.py", "tests"),
        ("hsconfig-1.0.0/src/hsconfig/test_hidden_contract.py", "tests"),
        ("hsconfig-1.0.0/src/hsconfig/hidden_contract_test.py", "tests"),
        ("hsconfig-1.0.0/src/hsconfig/conftest.py", "tests"),
        ("hsconfig-1.0.0/outputs/Deck/GlobalValues.json", "outputs"),
        ("hsconfig/.pytest_cache/v/cache/nodeids", "local_cache"),
        ("hsconfig/__pycache__/cli.cpython-311.pyc", "local_cache"),
        ("hsconfig-1.0.0/.superpowers/runtime/receipt.json", "superpowers"),
        ("hsconfig-1.0.0/runtime-evidence/Power.log", "runtime_evidence"),
        ("hsconfig-1.0.0/HEARTHRANGERLOGS/latest.log", "runtime_evidence"),
        ("hsconfig-1.0.0/HearthstoneLogs/latest.log", "runtime_evidence"),
        ("hsconfig-1.0.0/PRIVATE_RUNTIME/state.json", "runtime_evidence"),
        ("hsconfig-1.0.0/Runtime_Exports/config.json", "runtime_evidence"),
        ("hsconfig-1.0.0/session.hdtreplay", "runtime_evidence"),
        ("hsconfig-1.0.0/session.hsreplay", "runtime_evidence"),
    ],
)
def test_distribution_members_reject_non_runtime_content(
    member: str,
    reason: str,
) -> None:
    with pytest.raises(DistributionContentError, match=reason):
        validate_distribution_members("sdist", [member])


@pytest.mark.parametrize(
    ("member", "reason"),
    [
        ("/hsconfig/cli.py", "absolute_path"),
        ("C:/Users/operator/hsconfig/cli.py", "absolute_path"),
        ("hsconfig-1.0.0/../outside.txt", "path_traversal"),
        ("hsconfig-1.0.0/.env", "secret_like_filename"),
        ("hsconfig-1.0.0/credentials.json", "secret_like_filename"),
        ("hsconfig-1.0.0/api-token.txt", "secret_like_filename"),
        ("hsconfig-1.0.0/API_KEY.json", "secret_like_filename"),
        ("hsconfig-1.0.0/api-key/settings.json", "secret_like_filename"),
        ("hsconfig-1.0.0/token.json", "secret_like_filename"),
        ("hsconfig-1.0.0/ClientSecret/config.json", "secret_like_filename"),
        ("hsconfig-1.0.0/id_rsa", "secret_like_filename"),
        ("hsconfig-1.0.0/client.key", "secret_like_filename"),
    ],
)
def test_distribution_members_reject_unsafe_paths_and_secret_like_filenames(
    member: str,
    reason: str,
) -> None:
    with pytest.raises(DistributionContentError, match=reason):
        validate_distribution_members("sdist", [member])


def test_distribution_archive_selection_requires_one_wheel_and_one_sdist(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    wheel.touch()
    sdist.touch()

    assert _select_distribution_archives(tmp_path) == (wheel, sdist)

    (tmp_path / "hsconfig-1.0.0-2-py3-none-any.whl").touch()
    with pytest.raises(DistributionContentError, match="wheel_count:2"):
        _select_distribution_archives(tmp_path)


@pytest.mark.parametrize(
    "entry_type",
    [
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
        tarfile.FIFOTYPE,
    ],
)
def test_sdist_rejects_every_non_regular_tar_entry(
    tmp_path: Path,
    entry_type: bytes,
) -> None:
    archive_path = tmp_path / "hsconfig-1.0.0.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        entry = tarfile.TarInfo("hsconfig-1.0.0/src/hsconfig/unsafe.py")
        entry.type = entry_type
        entry.linkname = "hsconfig-1.0.0/src/hsconfig/cli.py"
        archive.addfile(entry)

    with pytest.raises(DistributionContentError, match="non_regular_tar_entry"):
        validate_distribution_archive("sdist", archive_path)


def test_sdist_validates_link_target_before_rejecting_link(tmp_path: Path) -> None:
    archive_path = tmp_path / "hsconfig-1.0.0.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        entry = tarfile.TarInfo("hsconfig-1.0.0/src/hsconfig/unsafe.py")
        entry.type = tarfile.SYMTYPE
        entry.linkname = "../../outside.py"
        archive.addfile(entry)

    with pytest.raises(DistributionContentError, match="path_traversal"):
        validate_distribution_archive("sdist", archive_path)


@pytest.mark.parametrize("mode", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR])
def test_wheel_rejects_non_regular_zip_entries(tmp_path: Path, mode: int) -> None:
    archive_path = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    info = zipfile.ZipInfo("hsconfig/unsafe.py")
    info.create_system = 3
    info.external_attr = (mode | 0o644) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "hsconfig/cli.py" if mode == stat.S_IFLNK else "")

    with pytest.raises(DistributionContentError, match="non_regular_zip_entry"):
        validate_distribution_archive("wheel", archive_path)


def test_wheel_validates_symlink_target_before_rejecting_link(tmp_path: Path) -> None:
    archive_path = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    info = zipfile.ZipInfo("hsconfig/unsafe.py")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, "../../outside.py")

    with pytest.raises(DistributionContentError, match="path_traversal"):
        validate_distribution_archive("wheel", archive_path)


def test_real_archives_accept_regular_files_and_expected_directories(
    tmp_path: Path,
) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    payload = b"from __future__ import annotations\n"
    _write_complete_sdist(sdist)

    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("hsconfig/", "")
        archive.writestr("hsconfig/__init__.py", payload)
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")

    validate_distribution_archive("sdist", sdist)
    validate_distribution_archive("wheel", wheel)


@pytest.mark.parametrize(
    ("filename", "reason"),
    [
        ("id_rsa.json", "secret_like_filename"),
        ("id_ed25519.backup.json", "secret_like_filename"),
        ("server.pem.json", "secret_like_filename"),
        ("client.key.json", "secret_like_filename"),
        ("HDT_runtime.xml.json", "runtime_evidence"),
        ("HDT.xml.json", "runtime_evidence"),
    ],
)
def test_real_archives_reject_concealed_secret_and_hdt_suffix_chains(
    tmp_path: Path,
    filename: str,
    reason: str,
) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        _add_tar_file(
            archive,
            f"hsconfig-1.0.0/src/hsconfig/{filename}",
            b"concealed",
        )
    with pytest.raises(DistributionContentError, match=reason):
        validate_distribution_archive("sdist", sdist)

    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"hsconfig/{filename}", "concealed")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
    with pytest.raises(DistributionContentError, match=reason):
        validate_distribution_archive("wheel", wheel)


@pytest.mark.parametrize(
    ("filename", "reason"),
    [
        ("x.id_rsa.json", "secret_like_filename"),
        ("backup.id_ed25519.json", "secret_like_filename"),
        ("archive.id_ed25519.py", "secret_like_filename"),
        ("server.ppk.json", "secret_like_filename"),
        ("client.jks.py", "secret_like_filename"),
        ("signing.keystore.pyi", "secret_like_filename"),
    ],
)
def test_complete_archives_reject_prefixed_ssh_and_keystore_suffix_chains(
    tmp_path: Path,
    filename: str,
    reason: str,
) -> None:
    relative = f"src/hsconfig/{filename}"
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    _write_complete_sdist(sdist, extra_files=(relative,))
    with pytest.raises(DistributionContentError, match=reason):
        validate_distribution_archive("sdist", sdist)

    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"hsconfig/{filename}", "concealed")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
    with pytest.raises(DistributionContentError, match=reason):
        validate_distribution_archive("wheel", wheel)


@pytest.mark.parametrize(
    "relative",
    [
        "src/hsconfig/Power.2026-08-04.log.json",
        "src/hsconfig/HearthRanger.2026-08-04.logs.json",
        "src/hsconfig/Hearthstone.build.42.log.json",
        "src/hsconfig/runtime.2026-08-04.evidence/payload.json",
        "src/hsconfig/runtime.build.42.exports/payload.json",
        "src/hsconfig/private.2026-08-04.runtime/payload.json",
    ],
)
def test_complete_archives_reject_semantic_evidence_tokens_across_rotations(
    tmp_path: Path,
    relative: str,
) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    _write_complete_sdist(sdist, extra_files=(relative,))
    with pytest.raises(DistributionContentError, match="runtime_evidence"):
        validate_distribution_archive("sdist", sdist)

    wheel_member = relative.removeprefix("src/")
    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(wheel_member, "concealed")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
    with pytest.raises(DistributionContentError, match="runtime_evidence"):
        validate_distribution_archive("wheel", wheel)


def test_sdist_required_init_must_be_regular_file(tmp_path: Path) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    _write_complete_sdist(sdist, init_as_directory=True)

    with pytest.raises(DistributionContentError, match="incomplete_sdist"):
        validate_distribution_archive("sdist", sdist)


@pytest.mark.parametrize("payload", [b"", b"not metadata\n"])
def test_sdist_rejects_empty_or_invalid_root_pkg_info(
    tmp_path: Path,
    payload: bytes,
) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    _write_complete_sdist(sdist, root_pkg_info=payload)

    with pytest.raises(DistributionContentError, match="invalid_pkg_info"):
        validate_distribution_archive("sdist", sdist)


def test_sdist_rejects_wrong_root_pkg_info_name(tmp_path: Path) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    _write_complete_sdist(
        sdist,
        root_pkg_info=b"Metadata-Version: 2.4\nName: other\nVersion: 1.0.0\n",
    )

    with pytest.raises(DistributionContentError, match="pkg_info_name_mismatch"):
        validate_distribution_archive("sdist", sdist)


def test_sdist_rejects_wrong_egg_info_version(tmp_path: Path) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    _write_complete_sdist(
        sdist,
        egg_pkg_info=b"Metadata-Version: 2.4\nName: hsconfig\nVersion: 2.0.0\n",
    )

    with pytest.raises(DistributionContentError, match="pkg_info_version_mismatch"):
        validate_distribution_archive("sdist", sdist)


@pytest.mark.parametrize(
    ("target", "metadata_version"),
    [
        ("root", ""),
        ("egg", "garbage"),
        ("root", "9.9"),
    ],
)
def test_sdist_rejects_unsupported_core_metadata_versions(
    tmp_path: Path,
    target: str,
    metadata_version: str,
) -> None:
    payload = (
        f"Metadata-Version: {metadata_version}\nName: hsconfig\nVersion: 1.0.0\n"
    ).encode()
    kwargs = (
        {"root_pkg_info": payload} if target == "root" else {"egg_pkg_info": payload}
    )
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    _write_complete_sdist(sdist, **kwargs)

    with pytest.raises(DistributionContentError, match="metadata_version"):
        validate_distribution_archive("sdist", sdist)


@pytest.mark.parametrize(
    "filename",
    ["runtime_evidence.json", "private_runtime.json", "HDT_runtime_export.xml"],
)
def test_real_archives_reject_runtime_evidence_file_stems(
    tmp_path: Path,
    filename: str,
) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        payload = b"evidence"
        entry = tarfile.TarInfo(f"hsconfig-1.0.0/src/hsconfig/{filename}")
        entry.size = len(payload)
        archive.addfile(entry, io.BytesIO(payload))
    with pytest.raises(DistributionContentError, match="runtime_evidence"):
        validate_distribution_archive("sdist", sdist)

    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"hsconfig/{filename}", "evidence")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
    with pytest.raises(DistributionContentError, match="runtime_evidence"):
        validate_distribution_archive("wheel", wheel)


@pytest.mark.parametrize(
    "filename",
    [
        "Power.log.json",
        "HearthRanger.log.json",
        "session.hdtreplay.json",
        "session.hsreplay.json",
        "HDT_export.xml.json",
    ],
)
def test_real_archives_reject_concealed_runtime_evidence_suffixes(
    tmp_path: Path,
    filename: str,
) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        payload = b"evidence"
        entry = tarfile.TarInfo(f"hsconfig-1.0.0/src/hsconfig/{filename}")
        entry.size = len(payload)
        archive.addfile(entry, io.BytesIO(payload))
    with pytest.raises(DistributionContentError, match="runtime_evidence"):
        validate_distribution_archive("sdist", sdist)

    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"hsconfig/{filename}", "evidence")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
    with pytest.raises(DistributionContentError, match="runtime_evidence"):
        validate_distribution_archive("wheel", wheel)


def test_wheel_licenses_allow_only_standard_license_filenames(tmp_path: Path) -> None:
    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("hsconfig/__init__.py", "")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
        archive.writestr(
            "hsconfig-1.0.0.dist-info/licenses/runtime_notes.json",
            "{}",
        )
    with pytest.raises(DistributionContentError, match="unexpected_wheel_content"):
        validate_distribution_archive("wheel", wheel)

    accepted = tmp_path / "hsconfig-1.0.0-1-py3-none-any.whl"
    with zipfile.ZipFile(accepted, "w") as archive:
        archive.writestr("hsconfig/__init__.py", "")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
        archive.writestr("hsconfig-1.0.0.dist-info/licenses/LICENSE.txt", "license")
    validate_distribution_archive("wheel", accepted)


@pytest.mark.parametrize("filename", ["LICENSE.Power.log", "LICENSE.HDT.xml"])
def test_wheel_rejects_concealed_nonstandard_license_names(
    tmp_path: Path,
    filename: str,
) -> None:
    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("hsconfig/__init__.py", "")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
        archive.writestr(f"hsconfig-1.0.0.dist-info/licenses/{filename}", "hidden")
    with pytest.raises(DistributionContentError):
        validate_distribution_archive("wheel", wheel)


def test_sdist_rejects_nested_unknown_egg_info_directory(tmp_path: Path) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        entry = tarfile.TarInfo("hsconfig-1.0.0/src/hsconfig.egg-info/evil")
        entry.type = tarfile.DIRTYPE
        archive.addfile(entry)

    with pytest.raises(DistributionContentError, match="unexpected_sdist_content"):
        validate_distribution_archive("sdist", sdist)


def test_sdist_rejects_metadata_only_incomplete_archive(tmp_path: Path) -> None:
    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        payload = b"Metadata-Version: 2.4\nName: hsconfig\nVersion: 1.0.0\n"
        entry = tarfile.TarInfo("hsconfig-1.0.0/PKG-INFO")
        entry.size = len(payload)
        archive.addfile(entry, io.BytesIO(payload))

    with pytest.raises(DistributionContentError, match="incomplete_sdist"):
        validate_distribution_archive("sdist", sdist)


@pytest.mark.parametrize(
    "member",
    [
        "hsconfig/./cli.py",
        "hsconfig//cli.py",
        "hsconfig/cli.py. ",
    ],
)
def test_wheel_rejects_noncanonical_member_paths(
    tmp_path: Path,
    member: str,
) -> None:
    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(member, "")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
    with pytest.raises(DistributionContentError, match="noncanonical_archive_path"):
        validate_distribution_archive("wheel", wheel)


def test_wheel_rejects_windows_casefold_collisions(tmp_path: Path) -> None:
    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("hsconfig/cli.py", "")
        archive.writestr("HSCONFIG/CLI.py", "")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
    with pytest.raises(DistributionContentError, match="windows_casefold_collision"):
        validate_distribution_archive("wheel", wheel)


def test_archives_reject_mixed_or_artifact_mismatched_roots(tmp_path: Path) -> None:
    wheel = tmp_path / "hsconfig-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("hsconfig/__init__.py", "")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
        archive.writestr("hsconfig-2.0.0.dist-info/WHEEL", "")
    with pytest.raises(DistributionContentError, match="archive_root_mismatch"):
        validate_distribution_archive("wheel", wheel)

    sdist = tmp_path / "hsconfig-1.0.0.tar.gz"
    with tarfile.open(sdist, "w:gz") as archive:
        for root in ("hsconfig-1.0.0", "hsconfig-2.0.0"):
            payload = b""
            entry = tarfile.TarInfo(f"{root}/src/hsconfig/__init__.py")
            entry.size = len(payload)
            archive.addfile(entry, io.BytesIO(payload))
    with pytest.raises(DistributionContentError, match="archive_root_mismatch"):
        validate_distribution_archive("sdist", sdist)

    wrong_distribution = tmp_path / "other-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wrong_distribution, "w") as archive:
        archive.writestr("hsconfig/__init__.py", "")
        archive.writestr("hsconfig-1.0.0.dist-info/METADATA", "Version: 1.0.0\n")
    with pytest.raises(DistributionContentError, match="distribution_mismatch"):
        validate_distribution_archive("wheel", wrong_distribution)


def test_source_staging_copies_regular_build_inputs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src/hsconfig").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[build-system]\n", encoding="utf-8")
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    (repo / "src/hsconfig/__init__.py").write_text(
        "VERSION = 'test'\n", encoding="utf-8"
    )

    staged = tmp_path / "staged"
    _stage_build_source(repo, staged)

    assert (staged / "pyproject.toml").read_text(encoding="utf-8") == "[build-system]\n"
    assert (staged / "README.md").read_text(encoding="utf-8") == "readme\n"
    assert (staged / "src/hsconfig/__init__.py").read_text(
        encoding="utf-8"
    ) == "VERSION = 'test'\n"


def test_source_staging_rejects_symlink_to_outside_secret(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "src/hsconfig").mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[build-system]\n", encoding="utf-8")
    (repo / "README.md").write_text("readme\n", encoding="utf-8")
    (repo / "src/hsconfig/__init__.py").write_text("", encoding="utf-8")
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("secret\n", encoding="utf-8")
    link = repo / "src/hsconfig/leak.py"
    try:
        link.symlink_to(secret)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"platform cannot create test symlink: {error}")

    with pytest.raises(DistributionVerificationError, match="unsafe_source_input"):
        _stage_build_source(repo, tmp_path / "staged")
    assert not (tmp_path / "staged/src/hsconfig/leak.py").exists()


def test_explicit_staged_sentinel_probe_requires_clean_status() -> None:
    _assert_supported_sentinel_result(
        {"status": "clean", "authority": "diagnostic_only", "apply_blocking": False}
    )
    with pytest.raises(
        DistributionVerificationError,
        match="supported_interface_not_clean",
    ):
        _assert_supported_sentinel_result(
            {
                "status": "drift_detected",
                "authority": "diagnostic_only",
                "apply_blocking": False,
            }
        )


def test_subprocess_environment_removes_hostile_python_and_pip_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(tmp_path / "hostile"))
    monkeypatch.setenv("PYTHONHOME", str(tmp_path / "fake-home"))
    monkeypatch.setenv("PIP_INDEX_URL", "https://attacker.invalid/simple")
    monkeypatch.setenv("PIP_CONFIG_FILE", str(tmp_path / "pip.ini"))
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://attacker.invalid/extra")
    result = _run(
        [
            sys.executable,
            "-c",
            (
                "import json, os; print(json.dumps({"
                "'PYTHONPATH': os.environ.get('PYTHONPATH'),"
                "'PYTHONHOME': os.environ.get('PYTHONHOME'),"
                "'PIP_INDEX_URL': os.environ.get('PIP_INDEX_URL'),"
                "'PIP_EXTRA_INDEX_URL': os.environ.get('PIP_EXTRA_INDEX_URL'),"
                "'PIP_CONFIG_FILE': os.environ.get('PIP_CONFIG_FILE'),"
                "'PYTHONDONTWRITEBYTECODE': os.environ.get('PYTHONDONTWRITEBYTECODE')"
                "}))"
            ),
        ],
        cwd=tmp_path,
    )
    environment = json.loads(result.stdout)

    assert environment == {
        "PYTHONPATH": None,
        "PYTHONHOME": None,
        "PIP_INDEX_URL": None,
        "PIP_EXTRA_INDEX_URL": None,
        "PIP_CONFIG_FILE": os.devnull,
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def test_smoke_module_must_resolve_inside_fresh_venv(tmp_path: Path) -> None:
    smoke_venv = tmp_path / "smoke-venv"
    installed = smoke_venv / "Lib/site-packages/hsconfig/__init__.py"
    installed.parent.mkdir(parents=True)
    installed.touch()

    _assert_installed_module_path(installed, smoke_venv)
    with pytest.raises(DistributionVerificationError, match="outside_smoke_venv"):
        _assert_installed_module_path(
            tmp_path / "live-repo/src/hsconfig/__init__.py",
            smoke_venv,
        )


def test_smoke_inventory_contains_only_wheel_dependencies_and_bootstrap_pip() -> None:
    _assert_smoke_inventory(
        [
            {"name": "certifi", "version": "2026.7.22"},
            {"name": "charset-normalizer", "version": "3.4.9"},
            {"name": "hsconfig", "version": "1.0.0"},
            {"name": "hearthstone", "version": "9.20.7"},
            {"name": "idna", "version": "3.18"},
            {"name": "PyYAML", "version": "6.0.3"},
            {"name": "pip", "version": "26.1.2"},
            {"name": "requests", "version": "2.34.2"},
            {"name": "urllib3", "version": "2.7.0"},
        ]
    )
    with pytest.raises(DistributionVerificationError, match="unexpected_package"):
        _assert_smoke_inventory(
            [
                {"name": "hsconfig", "version": "1.0.0"},
                {"name": "hearthstone", "version": "9.20.7"},
                {"name": "PyYAML", "version": "6.0.3"},
                {"name": "pip", "version": "26.1.2"},
                {"name": "pytest", "version": "9.1.1"},
            ]
        )


def test_status_gate_runs_after_isolated_verification_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statuses: list[str] = []

    def status(_root: Path) -> str:
        value = "unchanged\n"
        statuses.append(value)
        return value

    def fail(
        *_args: object, **_kwargs: object
    ) -> distribution.DistributionVerification:
        raise DistributionVerificationError("primary_failure")

    monkeypatch.setattr(distribution, "_git_status", status)
    monkeypatch.setattr(
        distribution,
        "_locked_versions",
        lambda _path: {
            "pip": "26.1.2",
            "build": "1.5.0",
            "setuptools": "83.0.0",
            "wheel": "0.47.0",
        },
    )
    monkeypatch.setattr(distribution, "_verify_distribution_in_temporary", fail)

    with pytest.raises(DistributionVerificationError, match="primary_failure"):
        distribution.verify_distribution(tmp_path)

    assert statuses == ["unchanged\n", "unchanged\n"]
    assert list(tmp_path.glob("hsconfig-distribution-*")) == []
