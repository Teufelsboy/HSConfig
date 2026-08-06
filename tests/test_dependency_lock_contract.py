from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tomllib

import pytest

from scripts import lock_wheel_closure as WHEEL_CLOSURE


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILENAMES = ("pylock.3.11.toml", "pylock.3.12.toml")
WHEEL_CLOSURE_SCRIPT = REPOSITORY_ROOT / "scripts" / "lock_wheel_closure.py"
CONTROLLED_PACKAGES = {
    "build",
    "hearthstone",
    "hypothesis",
    "pip",
    "pip-audit",
    "pytest",
    "pytest-cov",
    "pyyaml",
    "ruff",
    "setuptools",
    "wheel",
}
PIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*==[^=\s]+$")
PYTHON_VERSION_MARKER = re.compile(
    r"python_version\s*(==|!=)\s*['\"](\d+\.\d+)['\"]"
)


def _normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _load_lock(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _package_mapping(lock: dict[str, object]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for package in lock.get("packages", []):
        assert isinstance(package, dict)
        name = package.get("name")
        version = package.get("version")
        assert isinstance(name, str) and name
        assert isinstance(version, str) and version
        normalized = _normalized_name(name)
        assert normalized not in mapping
        mapping[normalized] = version
    return mapping


def _assert_archive_is_hashed(archive: object) -> None:
    assert isinstance(archive, dict)
    url = archive.get("url")
    hashes = archive.get("hashes")
    assert isinstance(url, str) and url.startswith("https://")
    assert "/" not in url.removeprefix("https://").split("/", 1)[0]
    assert "@" not in url
    assert isinstance(hashes, dict), "archive missing hashes"
    digest = hashes.get("sha256")
    assert isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)


def _is_universal_wheel(archive: object) -> bool:
    if not isinstance(archive, dict):
        return False
    name = str(archive.get("name", ""))
    if not name.endswith(".whl"):
        return False
    python_tag, abi_tag, platform_tag = name[:-4].rsplit("-", 3)[-3:]
    return (
        "py3" in python_tag.split(".")
        and abi_tag == "none"
        and platform_tag == "any"
    )


def _wheel_supports_target(archive: object, minor: str, platform: str) -> bool:
    if not isinstance(archive, dict):
        return False
    name = str(archive.get("name", ""))
    if not name.endswith(".whl"):
        return False
    python_tag, abi_tag, platform_tag = name[:-4].rsplit("-", 3)[-3:]
    compact_minor = minor.replace(".", "")
    interpreters = set(python_tag.split("."))
    abis = set(abi_tag.split("."))
    platforms = set(platform_tag.split("."))
    interpreter_compatible = bool(
        interpreters & {"py3", f"py{compact_minor}", f"cp{compact_minor}"}
    )
    abi_compatible = bool(abis & {"none", "abi3", f"cp{compact_minor}"})
    if platform == "windows-x64":
        platform_compatible = "any" in platforms or "win_amd64" in platforms
    else:
        platform_compatible = "any" in platforms or any(
            tag.endswith("_x86_64") and "manylinux" in tag for tag in platforms
        )
    return interpreter_compatible and abi_compatible and platform_compatible


def _assert_binary_target_closure(lock: dict[str, object], minor: str) -> None:
    for package in lock.get("packages", []):
        assert isinstance(package, dict)
        wheels = package.get("wheels", [])
        assert isinstance(wheels, list)
        for platform in ("windows-x64", "linux-x86_64"):
            assert any(
                _wheel_supports_target(wheel, minor, platform) for wheel in wheels
            ), f"{package.get('name')} lacks a compatible {platform} wheel"


def _assert_interpreter_environment(
    lock: dict[str, object], named_minor: str, other_minor: str
) -> str:
    markers: list[str] = []
    environment = lock.get("environment")
    if environment is not None:
        assert isinstance(environment, str), "unsupported environment surface"
        markers.append(environment)
    environments = lock.get("environments")
    if environments is not None:
        assert isinstance(environments, list), "unsupported environments surface"
        assert all(isinstance(marker, str) for marker in environments)
        markers.extend(environments)
    if not markers:
        return "external_filename_and_generation_evidence"

    def admits(minor: str, marker: str) -> bool:
        clauses = PYTHON_VERSION_MARKER.findall(marker)
        assert clauses, f"unsupported environment marker: {marker}"
        return all(
            (candidate == minor) if operator == "==" else (candidate != minor)
            for operator, candidate in clauses
        )

    assert any(admits(named_minor, marker) for marker in markers), (
        f"environment marker does not admit {named_minor}"
    )
    assert not any(admits(other_minor, marker) for marker in markers), (
        f"environment marker does not reject {other_minor}"
    )
    return "lock_marker"


def _assert_lock_is_safe(lock: dict[str, object]) -> None:
    assert lock.get("lock-version") == "1.0"
    for package in lock.get("packages", []):
        assert isinstance(package, dict)
        assert not package.get("editable", False), "editable entries are forbidden"
        assert not any(
            key in package for key in ("directory", "path", "vcs", "git", "source")
        )
        assert not str(package.get("name", "")).lower() == "hsconfig"
        archives = [*package.get("wheels", []), *([package["sdist"]] if "sdist" in package else [])]
        assert archives
        for archive in archives:
            _assert_archive_is_hashed(archive)
        if any(not _is_universal_wheel(wheel) for wheel in package.get("wheels", [])):
            assert "sdist" in package, "platform-specific wheel requires sdist fallback"


def test_checked_in_locks_classify_missing_environment_markers_as_external_provenance() -> None:
    locks = [_load_lock(REPOSITORY_ROOT / filename) for filename in LOCK_FILENAMES]

    assert _assert_interpreter_environment(locks[0], "3.11", "3.12") == (
        "external_filename_and_generation_evidence"
    )
    assert _assert_interpreter_environment(locks[1], "3.12", "3.11") == (
        "external_filename_and_generation_evidence"
    )


def _read_constraints(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == sorted(lines, key=lambda line: _normalized_name(line.split("==", 1)[0]))
    assert len(lines) == len(set(lines))
    assert all(PIN_PATTERN.fullmatch(line) for line in lines)
    return {
        _normalized_name(name): version
        for name, version in (line.split("==", maxsplit=1) for line in lines)
    }


def test_checked_in_dual_locks_match_controlled_dependency_contract() -> None:
    locks = [_load_lock(REPOSITORY_ROOT / filename) for filename in LOCK_FILENAMES]
    mappings = [_package_mapping(lock) for lock in locks]

    for lock, minor in zip(locks, ("3.11", "3.12"), strict=True):
        _assert_lock_is_safe(lock)
        _assert_binary_target_closure(lock, minor)
    assert mappings[0] == mappings[1]
    assert CONTROLLED_PACKAGES <= mappings[0].keys()
    assert "mutmut" not in mappings[0]
    assert _read_constraints(REPOSITORY_ROOT / "constraints-ci.txt") == mappings[0]


@pytest.mark.parametrize(
    ("contents", "message"),
    (
        (
            "lock-version = '1.0'\n[[packages]]\nname = 'fixture'\nversion = '1.0'\n[[packages.wheels]]\nurl = 'https://example.test/fixture.whl'\n",
            "hash",
        ),
        (
            "lock-version = '1.0'\n[[packages]]\nname = 'fixture'\nversion = '1.0'\neditable = true\n[[packages.wheels]]\nurl = 'https://example.test/fixture.whl'\n[packages.wheels.hashes]\nsha256 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n",
            "editable",
        ),
        (
            "lock-version = '1.0'\n[[packages]]\nname = 'fixture'\nversion = '1.0'\n[[packages.wheels]]\nname = 'fixture-1.0-cp311-cp311-win_amd64.whl'\nurl = 'https://example.test/fixture.whl'\n[packages.wheels.hashes]\nsha256 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n",
            "sdist",
        ),
    ),
)
def test_lock_validator_rejects_malformed_synthetic_lock(
    tmp_path: Path, contents: str, message: str
) -> None:
    path = tmp_path / "malformed.toml"
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(AssertionError, match=message):
        _assert_lock_is_safe(_load_lock(path))


def test_marker_environment_contract_admits_only_its_named_minor(tmp_path: Path) -> None:
    path = tmp_path / "marker.toml"
    path.write_text(
        "lock-version = '1.0'\nenvironments = [\"python_version == '3.11'\"]\n",
        encoding="utf-8",
    )
    lock = _load_lock(path)

    assert _assert_interpreter_environment(lock, "3.11", "3.12") == "lock_marker"
    with pytest.raises(AssertionError, match="does not admit"):
        _assert_interpreter_environment(lock, "3.12", "3.11")


def test_binary_target_closure_rejects_windows_only_native_package() -> None:
    lock = {
        "packages": [
            {
                "name": "native",
                "version": "1.0",
                "wheels": [
                    {"name": "native-1.0-cp311-cp311-win_amd64.whl"},
                ],
                "sdist": {"name": "native-1.0.tar.gz"},
            }
        ]
    }

    with pytest.raises(AssertionError, match="linux-x86_64 wheel"):
        _assert_binary_target_closure(lock, "3.11")


def test_lock_refresh_generates_and_validates_cross_platform_wheel_closure() -> None:
    script = (REPOSITORY_ROOT / "scripts" / "refresh_locks.ps1").read_text(
        encoding="utf-8"
    )

    assert "lock_wheel_closure.py" in script
    assert "$lockAugmenterContent" not in script
    assert "append_compatible_wheels" not in script
    assert "wheel_supports_target" not in script
    assert "--only-binary=:all:" in script
    assert "--no-build-isolation" in script
    assert "$case.VenvPython" in script
    assert "'pylock.toml'" in script


def test_wheel_closure_authority_has_an_executable_stdlib_cli() -> None:
    completed = subprocess.run(
        [sys.executable, str(WHEEL_CLOSURE_SCRIPT), "--help"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "wheel" in completed.stdout.casefold()


def _release_file(filename: str, digest: str, *, package_type: str = "bdist_wheel") -> dict[str, object]:
    return {
        "filename": filename,
        "url": f"https://files.example.invalid/{filename}",
        "packagetype": package_type,
        "yanked": False,
        "digests": {"sha256": digest},
    }


@pytest.mark.parametrize("minor", ("3.11", "3.12"))
def test_wheel_authority_selects_one_deterministic_artifact_per_missing_target(
    minor: str,
) -> None:
    compact = minor.replace(".", "")
    package = {
        "name": "native",
        "version": "1.0",
        "wheels": [
            {
                "name": f"native-1.0-cp{compact}-cp{compact}-win_amd64.whl",
                "url": "https://files.example.invalid/native-win.whl",
                "hashes": {"sha256": "1" * 64},
            }
        ],
    }
    files = [
        _release_file("native-1.0.tar.gz", "2" * 64, package_type="sdist"),
        _release_file(
            f"native-1.0-cp{compact}-cp{compact}-manylinux_2_28_x86_64.whl",
            "3" * 64,
        ),
        _release_file(
            f"native-1.0-cp{compact}-cp{compact}-manylinux_2_17_x86_64.whl",
            "4" * 64,
        ),
    ]

    selected = WHEEL_CLOSURE.select_missing_wheels(package, minor, files)

    assert selected == (
        {
            "name": f"native-1.0-cp{compact}-cp{compact}-manylinux_2_17_x86_64.whl",
            "url": (
                "https://files.example.invalid/"
                f"native-1.0-cp{compact}-cp{compact}-manylinux_2_17_x86_64.whl"
            ),
            "sha256": "4" * 64,
        },
    )


def test_wheel_authority_rejects_future_manylinux_and_sdist_fallbacks() -> None:
    package = {"name": "native", "version": "1.0", "wheels": []}
    files = [
        _release_file("native-1.0-cp311-cp311-win_amd64.whl", "1" * 64),
        _release_file(
            "native-1.0-cp311-cp311-manylinux_2_40_x86_64.whl", "2" * 64
        ),
        _release_file("native-1.0.tar.gz", "3" * 64, package_type="sdist"),
    ]

    with pytest.raises(WHEEL_CLOSURE.WheelClosureError, match="linux-x86_64"):
        WHEEL_CLOSURE.select_missing_wheels(package, "3.11", files)


def test_wheel_authority_fails_before_replacing_any_lock_when_target_is_missing(
    tmp_path: Path,
) -> None:
    lock_template = """\
lock-version = "1.0"
[[packages]]
name = "native"
version = "1.0"
[[packages.wheels]]
name = "native-1.0-cp{compact}-cp{compact}-win_amd64.whl"
url = "https://files.example.invalid/native-win.whl"
[packages.wheels.hashes]
sha256 = "{digest}"
"""
    locks: dict[str, Path] = {}
    original: dict[str, bytes] = {}
    for minor, digest in (("3.11", "1" * 64), ("3.12", "2" * 64)):
        path = tmp_path / f"pylock.{minor}.toml"
        path.write_text(
            lock_template.format(compact=minor.replace(".", ""), digest=digest),
            encoding="utf-8",
        )
        locks[minor] = path
        original[minor] = path.read_bytes()
    constraints = tmp_path / "constraints-ci.txt"

    def missing_linux(_name: str, _version: str) -> list[dict[str, object]]:
        return []

    with pytest.raises(WHEEL_CLOSURE.WheelClosureError, match="linux-x86_64"):
        WHEEL_CLOSURE.update_lock_files(
            locks,
            constraints,
            release_provider=missing_linux,
            required_packages={"native"},
        )

    assert {minor: path.read_bytes() for minor, path in locks.items()} == original
    assert not constraints.exists()
