"""One-snapshot verification boundary for complete configure runs."""

from __future__ import annotations

import json
from types import MappingProxyType
from typing import Any

from hsconfig.configure_run_stage_contract import (
    validate_configure_run_stage_files,
)
from hsconfig.package_domain import canonical_relative_path
from hsconfig.package_model import PackageView
from hsconfig.run_manifest import (
    MAX_RUN_FILES,
    TreeManifest,
    canonical_run_relative_path,
    validate_run_paths,
    verify_tree_manifest,
)


class _SnapshotPackageView:
    __slots__ = ("_files", "_names")

    def __init__(self, files: dict[str, bytes]) -> None:
        copied = {
            path: bytes(content)
            for path, content in sorted(files.items())
        }
        self._files = MappingProxyType(copied)
        self._names = tuple(copied)

    def file_names(self) -> tuple[str, ...]:
        return self._names

    def read_bytes(self, relative_path: str) -> bytes:
        try:
            return self._files[canonical_relative_path(relative_path)]
        except KeyError as error:
            raise FileNotFoundError(relative_path) from error

    def read_json(self, relative_path: str) -> Any:
        return json.loads(self.read_bytes(relative_path).decode("utf-8"))

    def exists(self, relative_path: str) -> bool:
        try:
            path = canonical_relative_path(relative_path)
        except ValueError:
            return False
        return path in self._files


class _PackageSubtreeView:
    __slots__ = ("_prefix", "_snapshot", "_names")

    def __init__(
        self,
        snapshot: _SnapshotPackageView,
        *,
        prefix: str,
    ) -> None:
        self._snapshot = snapshot
        self._prefix = prefix
        self._names = tuple(
            name[len(prefix) :]
            for name in snapshot.file_names()
            if name.startswith(prefix)
        )
        if not self._names:
            raise ValueError("run_package_subtree_missing")

    def file_names(self) -> tuple[str, ...]:
        return self._names

    def read_bytes(self, relative_path: str) -> bytes:
        path = canonical_relative_path(relative_path)
        return self._snapshot.read_bytes(f"{self._prefix}{path}")

    def read_json(self, relative_path: str) -> Any:
        return json.loads(self.read_bytes(relative_path).decode("utf-8"))

    def exists(self, relative_path: str) -> bool:
        try:
            path = canonical_relative_path(relative_path)
        except ValueError:
            return False
        return path in self._names


def verify_configure_run_package(
    revision: PackageView,
) -> tuple[TreeManifest, PackageView]:
    """Snapshot and verify a run, returning only its verified package view.

    ``PackageView`` has no stat/size operation, so byte-size limits can only be
    enforced after each file has been read. Task 3's filesystem publication
    boundary is responsible for pre-read physical resource controls.
    """

    try:
        names = tuple(revision.file_names())
        if len(names) > MAX_RUN_FILES or len(names) != len(set(names)):
            raise ValueError("duplicate run path")
        canonical_names = tuple(
            canonical_run_relative_path(name) for name in names
        )
        if canonical_names != names:
            raise ValueError("noncanonical run path")
        validate_run_paths(names)
        snapshot = _SnapshotPackageView(
            {
                name: bytes(revision.read_bytes(name))
                for name in names
            }
        )
        manifest = verify_tree_manifest(snapshot)
        package_aliases = tuple(
            name
            for name in snapshot.file_names()
            if name.casefold() == "04_package"
            or name.casefold().startswith("04_package/")
        )
        if any(
            not name.startswith("04_package/")
            for name in package_aliases
        ):
            raise ValueError("noncanonical package subtree")
        validate_configure_run_stage_files(
            deck_name=manifest.deck_name,
            deck_fingerprint=manifest.deck_fingerprint,
            stage_files={
                name: snapshot.read_bytes(name)
                for name in snapshot.file_names()
                if name != "package_manifest.json"
                and not name.startswith("04_package/")
            },
        )
        package = _PackageSubtreeView(
            snapshot,
            prefix="04_package/",
        )
        return manifest, package
    except Exception as error:
        raise ValueError("run_manifest_invalid") from error


__all__ = ("verify_configure_run_package",)
