from __future__ import annotations

from pathlib import Path
import re
import tomllib

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LOCK_FILENAMES = ("pylock.3.11.toml", "pylock.3.12.toml")
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
    return isinstance(archive, dict) and str(archive.get("name", "")).endswith(
        "-py3-none-any.whl"
    )


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

    for lock in locks:
        _assert_lock_is_safe(lock)
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
