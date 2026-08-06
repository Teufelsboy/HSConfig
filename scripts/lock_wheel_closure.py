"""Materialize the deterministic dual-platform wheel closure for release locks."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import json
from pathlib import Path
import re
import tomllib
import urllib.parse
import urllib.request


SUPPORTED_MINORS = ("3.11", "3.12")
TARGETS = ("windows-x64", "linux-x86_64")
MAX_MANYLINUX_GLIBC = (2, 39)
REQUIRED_PACKAGES = {
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
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PACKAGE_BLOCK = re.compile(r"(?ms)^\[\[packages\]\]\n.*?(?=^\[\[packages\]\]|\Z)")


class WheelClosureError(RuntimeError):
    """The lock cannot be closed without an sdist or unsupported wheel."""


ReleaseProvider = Callable[[str, str], Sequence[Mapping[str, object]]]


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).casefold()


def _wheel_tags(filename: str) -> tuple[set[str], set[str], set[str]] | None:
    if not filename.endswith(".whl"):
        return None
    try:
        python_tag, abi_tag, platform_tag = filename[:-4].rsplit("-", 3)[-3:]
    except ValueError:
        return None
    return set(python_tag.split(".")), set(abi_tag.split(".")), set(
        platform_tag.split(".")
    )


def _interpreter_compatible(interpreters: set[str], abis: set[str], minor: str) -> bool:
    compact = minor.replace(".", "")
    if interpreters & {"py3", f"py{compact}", f"cp{compact}"}:
        return bool(abis & {"none", "abi3", f"cp{compact}"})
    if "abi3" not in abis:
        return False
    return any(
        tag.startswith("cp3")
        and tag[2:].isdigit()
        and int(tag[2:]) <= int(compact)
        for tag in interpreters
    )


def _manylinux_policy_allows(platforms: set[str]) -> bool:
    legacy = {
        "manylinux1_x86_64": (2, 5),
        "manylinux2010_x86_64": (2, 12),
        "manylinux2014_x86_64": (2, 17),
    }
    versions = [legacy[tag] for tag in platforms if tag in legacy]
    versions.extend(
        (int(match.group(1)), int(match.group(2)))
        for tag in platforms
        if (match := re.fullmatch(r"manylinux_(\d+)_(\d+)_x86_64", tag))
    )
    return any(version <= MAX_MANYLINUX_GLIBC for version in versions)


def wheel_supports_target(filename: str, minor: str, target: str) -> bool:
    if minor not in SUPPORTED_MINORS or target not in TARGETS:
        raise WheelClosureError("unsupported wheel target")
    tags = _wheel_tags(filename)
    if tags is None:
        return False
    interpreters, abis, platforms = tags
    if not _interpreter_compatible(interpreters, abis, minor):
        return False
    if "any" in platforms:
        return True
    if target == "windows-x64":
        return "win_amd64" in platforms
    return _manylinux_policy_allows(platforms)


def _release_wheel(item: Mapping[str, object]) -> dict[str, str] | None:
    if item.get("packagetype") != "bdist_wheel" or item.get("yanked", False):
        return None
    filename = item.get("filename")
    url = item.get("url")
    digests = item.get("digests")
    digest = digests.get("sha256") if isinstance(digests, Mapping) else None
    if (
        not isinstance(filename, str)
        or not isinstance(url, str)
        or not url.startswith("https://")
        or "@" in url
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
    ):
        raise WheelClosureError("release wheel metadata is unsafe")
    return {"name": filename, "url": url, "sha256": digest}


def select_missing_wheels(
    package: Mapping[str, object],
    minor: str,
    release_files: Sequence[Mapping[str, object]],
) -> tuple[dict[str, str], ...]:
    wheels = package.get("wheels", [])
    if not isinstance(wheels, list):
        raise WheelClosureError("package wheel set is invalid")
    existing = {
        str(wheel.get("name", ""))
        for wheel in wheels
        if isinstance(wheel, Mapping)
    }
    candidates = sorted(
        (wheel for item in release_files if (wheel := _release_wheel(item)) is not None),
        key=lambda wheel: wheel["name"],
    )
    selected: list[dict[str, str]] = []
    for target in TARGETS:
        if any(wheel_supports_target(name, minor, target) for name in existing):
            continue
        compatible = [
            wheel
            for wheel in candidates
            if wheel_supports_target(wheel["name"], minor, target)
        ]
        if not compatible:
            raise WheelClosureError(
                f"binary target closure missing:{package.get('name')}:{target}"
            )
        chosen = compatible[0]
        if chosen["name"] not in existing:
            selected.append(chosen)
            existing.add(chosen["name"])
    return tuple(selected)


def _append_selected_wheels(
    source: str,
    package_name: str,
    selected: Sequence[Mapping[str, str]],
) -> str:
    matched = False

    def replace(match: re.Match[str]) -> str:
        nonlocal matched
        block = match.group(0)
        parsed = tomllib.loads(block)
        package = parsed["packages"][0]
        if package.get("name") != package_name:
            return block
        matched = True
        if not selected:
            return block
        additions = "".join(
            "\n[[packages.wheels]]\n"
            f"name = {json.dumps(wheel['name'])}\n"
            f"url = {json.dumps(wheel['url'])}\n\n"
            "[packages.wheels.hashes]\n"
            f"sha256 = {json.dumps(wheel['sha256'])}\n"
            for wheel in selected
        )
        before, marker, after = block.partition("[packages.sdist]")
        if marker:
            return before.rstrip("\n") + additions + "\n" + marker + after
        return block.rstrip("\n") + additions

    result = _PACKAGE_BLOCK.sub(replace, source)
    if not matched:
        raise WheelClosureError(f"package not found:{package_name}")
    return result


def _validate_archive(archive: object) -> None:
    if not isinstance(archive, Mapping):
        raise WheelClosureError("lock archive is invalid")
    url = archive.get("url")
    hashes = archive.get("hashes")
    digest = hashes.get("sha256") if isinstance(hashes, Mapping) else None
    if (
        not isinstance(url, str)
        or not url.startswith("https://")
        or "@" in url
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
    ):
        raise WheelClosureError("lock archive is unsafe")


def validate_lock(
    lock: Mapping[str, object], minor: str, required_packages: set[str]
) -> dict[str, str]:
    if lock.get("lock-version") != "1.0":
        raise WheelClosureError("unsupported lock version")
    mapping: dict[str, str] = {}
    packages = lock.get("packages")
    if not isinstance(packages, list):
        raise WheelClosureError("lock package list is invalid")
    for package in packages:
        if not isinstance(package, Mapping):
            raise WheelClosureError("lock package is invalid")
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise WheelClosureError("lock package is unversioned")
        normalized = normalize_name(name)
        if normalized == "hsconfig" or normalized in mapping:
            raise WheelClosureError("lock package identity is invalid")
        if package.get("editable") or any(
            key in package for key in ("directory", "path", "vcs", "git", "source")
        ):
            raise WheelClosureError("lock package source is unsafe")
        wheels = package.get("wheels")
        if not isinstance(wheels, list) or not wheels:
            raise WheelClosureError(f"binary target closure missing:{normalized}")
        for wheel in wheels:
            _validate_archive(wheel)
        if "sdist" in package:
            _validate_archive(package["sdist"])
        for target in TARGETS:
            if not any(
                isinstance(wheel, Mapping)
                and wheel_supports_target(str(wheel.get("name", "")), minor, target)
                for wheel in wheels
            ):
                raise WheelClosureError(
                    f"binary target closure missing:{normalized}:{target}"
                )
        mapping[normalized] = version
    missing = required_packages - mapping.keys()
    if missing:
        raise WheelClosureError("required packages missing:" + ",".join(sorted(missing)))
    if "mutmut" in mapping:
        raise WheelClosureError("mutmut is forbidden")
    return mapping


def _validate_bootstrap_pip(
    lock: Mapping[str, object], expected: Mapping[str, str]
) -> None:
    packages = lock.get("packages")
    if not isinstance(packages, list):
        raise WheelClosureError("bootstrap pip package list is invalid")
    records = [
        package
        for package in packages
        if isinstance(package, Mapping) and package.get("name") == "pip"
    ]
    if len(records) != 1 or records[0].get("version") != expected["version"]:
        raise WheelClosureError("bootstrap pip version mismatch")
    wheels = records[0].get("wheels")
    if not isinstance(wheels, list):
        raise WheelClosureError("bootstrap pip wheel set is invalid")
    matched = [
        wheel
        for wheel in wheels
        if isinstance(wheel, Mapping) and wheel.get("name") == expected["name"]
    ]
    if len(matched) != 1:
        raise WheelClosureError("bootstrap pip wheel missing")
    hashes = matched[0].get("hashes")
    if (
        matched[0].get("url") != expected["url"]
        or not isinstance(hashes, Mapping)
        or hashes.get("sha256") != expected["sha256"]
    ):
        raise WheelClosureError("bootstrap pip binding mismatch")


def _augment_lock(
    source: str,
    minor: str,
    release_provider: ReleaseProvider,
    required_packages: set[str],
) -> tuple[str, dict[str, str]]:
    try:
        lock = tomllib.loads(source)
    except tomllib.TOMLDecodeError as exc:
        raise WheelClosureError("lock TOML is invalid") from exc
    packages = lock.get("packages")
    if not isinstance(packages, list):
        raise WheelClosureError("lock package list is invalid")
    result = source
    for package in packages:
        if not isinstance(package, Mapping):
            raise WheelClosureError("lock package is invalid")
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise WheelClosureError("lock package is unversioned")
        selected = select_missing_wheels(
            package,
            minor,
            release_provider(name, version),
        )
        result = _append_selected_wheels(result, name, selected)
    mapping = validate_lock(tomllib.loads(result), minor, required_packages)
    return result.rstrip("\n") + "\n", mapping


def update_lock_files(
    lock_paths: Mapping[str, Path],
    constraints_path: Path,
    *,
    release_provider: ReleaseProvider,
    required_packages: set[str] = REQUIRED_PACKAGES,
    expected_pip: Mapping[str, str] | None = None,
) -> None:
    if set(lock_paths) != set(SUPPORTED_MINORS):
        raise WheelClosureError("exact Python minor locks are required")
    materialized: dict[str, str] = {}
    mappings: dict[str, dict[str, str]] = {}
    for minor in SUPPORTED_MINORS:
        source = lock_paths[minor].read_text(encoding="utf-8")
        materialized[minor], mappings[minor] = _augment_lock(
            source,
            minor,
            release_provider,
            required_packages,
        )
        if expected_pip is not None:
            _validate_bootstrap_pip(tomllib.loads(materialized[minor]), expected_pip)
    if mappings["3.11"] != mappings["3.12"]:
        raise WheelClosureError("interpreter dependency versions differ")
    constraints = "".join(
        f"{name}=={version}\n" for name, version in sorted(mappings["3.11"].items())
    )
    for minor in SUPPORTED_MINORS:
        lock_paths[minor].write_text(materialized[minor], encoding="utf-8", newline="\n")
    constraints_path.write_text(constraints, encoding="utf-8", newline="\n")


def _pypi_release_provider(name: str, version: str) -> Sequence[Mapping[str, object]]:
    url = "https://pypi.org/pypi/{}/{}/json".format(
        urllib.parse.quote(name, safe=""), urllib.parse.quote(version, safe="")
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    urls = payload.get("urls") if isinstance(payload, Mapping) else None
    if not isinstance(urls, list):
        raise WheelClosureError("PyPI release metadata is invalid")
    return urls


def _metadata_provider(root: Path) -> ReleaseProvider:
    def provide(name: str, version: str) -> Sequence[Mapping[str, object]]:
        path = root / f"{normalize_name(name)}-{version}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        urls = payload.get("urls") if isinstance(payload, Mapping) else payload
        if not isinstance(urls, list):
            raise WheelClosureError("synthetic release metadata is invalid")
        return urls

    return provide


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-311", required=True, type=Path)
    parser.add_argument("--lock-312", required=True, type=Path)
    parser.add_argument("--constraints", required=True, type=Path)
    parser.add_argument("--metadata-dir", type=Path)
    parser.add_argument("--pip-version", required=True)
    parser.add_argument("--pip-wheel-name", required=True)
    parser.add_argument("--pip-wheel-url", required=True)
    parser.add_argument("--pip-wheel-sha256", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    provider = (
        _metadata_provider(args.metadata_dir)
        if args.metadata_dir is not None
        else _pypi_release_provider
    )
    try:
        update_lock_files(
            {"3.11": args.lock_311, "3.12": args.lock_312},
            args.constraints,
            release_provider=provider,
            expected_pip={
                "version": args.pip_version,
                "name": args.pip_wheel_name,
                "url": args.pip_wheel_url,
                "sha256": args.pip_wheel_sha256,
            },
        )
    except (OSError, ValueError, WheelClosureError) as exc:
        print(str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
