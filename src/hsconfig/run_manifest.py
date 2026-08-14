"""Canonical full-tree manifests for rendered configure runs."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hsconfig.package_domain import canonical_relative_path
from hsconfig.package_model import PackageView

if TYPE_CHECKING:
    from hsconfig.configure_run_model import RenderedConfigureRun
    from hsconfig.package_render_authority import AuthorityArtifact


MANIFEST_PATH = "package_manifest.json"
SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_RUN_FILES = 100_000
MAX_RUN_TOTAL_BYTES = 16 * 1024 * 1024 * 1024
MAX_RUN_PATH_BYTES = 4096
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "deck_name",
        "deck_fingerprint",
        "entries",
        "content_root_sha256",
    }
)
_ENTRY_KEYS = frozenset({"relative_path", "size", "sha256"})
_WINDOWS_DEVICE_NAMES = frozenset(
    {
        "aux",
        "con",
        "nul",
        "prn",
        *(f"com{index}" for index in range(1, 10)),
        *(f"lpt{index}" for index in range(1, 10)),
    }
)


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    relative_path: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        try:
            path = canonical_run_relative_path(self.relative_path)
        except (TypeError, ValueError) as error:
            raise ValueError("run_manifest_entry_path_invalid") from error
        folded_path = path.casefold()
        if (
            folded_path == MANIFEST_PATH.casefold()
            or folded_path.startswith(f"{MANIFEST_PATH.casefold()}/")
        ):
            raise ValueError("run_manifest_self_entry_forbidden")
        if type(self.size) is not int or self.size < 0:
            raise ValueError("run_manifest_entry_size_invalid")
        if not _is_sha256(self.sha256):
            raise ValueError("run_manifest_entry_sha256_invalid")
        object.__setattr__(self, "relative_path", path)


@dataclass(frozen=True, slots=True)
class TreeManifest:
    schema_version: int
    deck_name: str
    deck_fingerprint: str
    entries: tuple[ManifestEntry, ...]
    content_root_sha256: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("run_manifest_schema_invalid")
        if (
            not isinstance(self.deck_name, str)
            or not self.deck_name
            or self.deck_name != self.deck_name.strip()
        ):
            raise ValueError("run_manifest_deck_name_invalid")
        if not _is_sha256(self.deck_fingerprint):
            raise ValueError("run_manifest_deck_fingerprint_invalid")
        if not isinstance(self.entries, tuple) or any(
            not isinstance(entry, ManifestEntry) for entry in self.entries
        ):
            raise TypeError("run_manifest_entries_invalid")
        paths = tuple(entry.relative_path for entry in self.entries)
        if (
            paths != tuple(sorted(paths))
            or len(paths) != len(set(paths))
            or len(paths) >= MAX_RUN_FILES
        ):
            raise ValueError("run_manifest_entries_not_unique_sorted")
        validate_run_paths(paths)
        if (
            not _is_sha256(self.content_root_sha256)
            or _content_root_sha256(self.entries)
            != self.content_root_sha256
        ):
            raise ValueError("run_manifest_content_root_invalid")


def build_tree_manifest(rendered: RenderedConfigureRun) -> TreeManifest:
    """Build schema-1 metadata for every non-manifest run artifact."""

    return build_tree_manifest_from_artifacts(
        deck_name=rendered.model.deck_name,
        deck_fingerprint=rendered.model.deck_fingerprint,
        artifacts=rendered.artifacts,
    )


def build_tree_manifest_from_artifacts(
    *,
    deck_name: str,
    deck_fingerprint: str,
    artifacts: tuple[AuthorityArtifact, ...],
) -> TreeManifest:
    """Build schema-1 metadata directly from finalized run content."""

    entries = tuple(
        ManifestEntry(
            relative_path=artifact.relative_path,
            size=artifact.size,
            sha256=artifact.sha256,
        )
        for artifact in sorted(
            (
                artifact
                for artifact in artifacts
                if artifact.relative_path != MANIFEST_PATH
            ),
            key=lambda artifact: artifact.relative_path,
        )
    )
    return TreeManifest(
        schema_version=SCHEMA_VERSION,
        deck_name=deck_name,
        deck_fingerprint=deck_fingerprint,
        entries=entries,
        content_root_sha256=_content_root_sha256(entries),
    )


def write_tree_manifest(manifest: TreeManifest) -> bytes:
    """Serialize one manifest to canonical UTF-8 JSON with a final LF."""

    if not isinstance(manifest, TreeManifest):
        raise TypeError("tree_manifest_required")
    payload = {
        "schema_version": manifest.schema_version,
        "deck_name": manifest.deck_name,
        "deck_fingerprint": manifest.deck_fingerprint,
        "entries": [
            {
                "relative_path": entry.relative_path,
                "size": entry.size,
                "sha256": entry.sha256,
            }
            for entry in manifest.entries
        ],
        "content_root_sha256": manifest.content_root_sha256,
    }
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def verify_tree_manifest(revision: PackageView) -> TreeManifest:
    """Verify manifest schema, identity, membership, bytes, and root hash."""

    try:
        names = tuple(revision.file_names())
        if (
            len(names) != len(set(names))
            or MANIFEST_PATH not in names
            or len(names) > MAX_RUN_FILES
        ):
            raise ValueError("membership")
        canonical_names = tuple(
            canonical_run_relative_path(name) for name in names
        )
        if canonical_names != names:
            raise ValueError("noncanonical names")
        validate_run_paths(names)
        files = {
            name: bytes(revision.read_bytes(name))
            for name in names
        }
        manifest_bytes = files[MANIFEST_PATH]
        if (
            len(manifest_bytes) > MAX_MANIFEST_BYTES
            or sum(len(content) for content in files.values())
            > MAX_RUN_TOTAL_BYTES
        ):
            raise ValueError("resource bounds")
        payload = json.loads(
            manifest_bytes.decode("utf-8"),
            object_pairs_hook=_unique_json_object,
        )
        manifest = _parse_tree_manifest(payload)
        expected_names = tuple(
            sorted(
                (
                    MANIFEST_PATH,
                    *(entry.relative_path for entry in manifest.entries),
                )
            )
        )
        if tuple(sorted(names)) != expected_names:
            raise ValueError("membership")
        for entry in manifest.entries:
            content = files[entry.relative_path]
            if (
                len(content) != entry.size
                or hashlib.sha256(content).hexdigest() != entry.sha256
            ):
                raise ValueError("content")
        if manifest_bytes != write_tree_manifest(manifest):
            raise ValueError("noncanonical manifest bytes")
        _verify_manifest_identity(manifest, files)
        return manifest
    except Exception as error:
        raise ValueError("run_manifest_invalid") from error


def _parse_tree_manifest(payload: Any) -> TreeManifest:
    if not isinstance(payload, dict) or set(payload) != _MANIFEST_KEYS:
        raise ValueError("schema")
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list):
        raise ValueError("entries")
    entries: list[ManifestEntry] = []
    for row in raw_entries:
        if not isinstance(row, dict) or set(row) != _ENTRY_KEYS:
            raise ValueError("entry")
        entries.append(
            ManifestEntry(
                relative_path=row["relative_path"],
                size=row["size"],
                sha256=row["sha256"],
            )
        )
    return TreeManifest(
        schema_version=payload["schema_version"],
        deck_name=payload["deck_name"],
        deck_fingerprint=payload["deck_fingerprint"],
        entries=tuple(entries),
        content_root_sha256=payload["content_root_sha256"],
    )


def _verify_manifest_identity(
    manifest: TreeManifest,
    files: dict[str, bytes],
) -> None:
    identity = _mapping_json(
        files["04_package/reports/deck_identity.json"]
    )
    summary = _mapping_json(files["configure_summary.json"])
    expected = (manifest.deck_name, manifest.deck_fingerprint)
    if (
        (identity.get("deck_name"), identity.get("deck_fingerprint"))
        != expected
        or (summary.get("deck_name"), summary.get("deck_fingerprint"))
        != expected
    ):
        raise ValueError("identity")


def _mapping_json(content: bytes) -> dict[str, Any]:
    payload = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=_unique_json_object,
    )
    if not isinstance(payload, dict):
        raise ValueError("mapping required")
    return payload


def _content_root_sha256(entries: tuple[ManifestEntry, ...]) -> str:
    records = b"".join(
        (
            f"{entry.relative_path}\0{entry.size}\0{entry.sha256}\n"
        ).encode("utf-8")
        for entry in entries
    )
    return hashlib.sha256(records).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def canonical_run_relative_path(value: str) -> str:
    path = canonical_relative_path(value)
    if (
        len(path.encode("utf-8")) > MAX_RUN_PATH_BYTES
        or unicodedata.normalize("NFC", path) != path
        or any(character in '?*"<>|' for character in path)
        or any(
            unicodedata.category(character).startswith("C")
            for character in path
        )
    ):
        raise ValueError("run_manifest_path_ambiguous")
    for part in path.split("/"):
        if (
            part.endswith((".", " "))
            or part.split(".", 1)[0].rstrip(" .").casefold()
            in _WINDOWS_DEVICE_NAMES
        ):
            raise ValueError("run_manifest_path_ambiguous")
    return path


def validate_run_paths(paths: tuple[str, ...]) -> None:
    canonical = tuple(canonical_run_relative_path(path) for path in paths)
    if len(canonical) > MAX_RUN_FILES or len(canonical) != len(set(canonical)):
        raise ValueError("run_manifest_path_duplicate")
    folded = tuple(path.casefold() for path in canonical)
    if len(folded) != len(set(folded)):
        raise ValueError("run_manifest_path_casefold_collision")
    files = set(folded)
    directory_spellings: dict[str, str] = {}
    for path in folded:
        parts = path.split("/")
        if any(
            "/".join(parts[:index]) in files
            for index in range(1, len(parts))
        ):
            raise ValueError("run_manifest_entry_path_collision")
    for path in canonical:
        parts = path.split("/")
        for index in range(1, len(parts)):
            directory = "/".join(parts[:index])
            folded_directory = directory.casefold()
            prior = directory_spellings.setdefault(
                folded_directory,
                directory,
            )
            if prior != directory:
                raise ValueError(
                    "run_manifest_directory_casefold_collision"
                )


def _unique_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


__all__ = (
    "MANIFEST_PATH",
    "ManifestEntry",
    "TreeManifest",
    "build_tree_manifest",
    "build_tree_manifest_from_artifacts",
    "canonical_run_relative_path",
    "validate_run_paths",
    "verify_tree_manifest",
    "write_tree_manifest",
)
