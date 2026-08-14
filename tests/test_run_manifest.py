from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

import pytest

import hsconfig.run_manifest as run_manifest
from hsconfig.configure_run_model import (
    RenderedConfigureRun,
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.run_manifest import (
    ManifestEntry,
    TreeManifest,
    build_tree_manifest,
    verify_tree_manifest,
    write_tree_manifest,
)
from tests.helpers.audited_package_request import audited_request


class MemoryPackageView:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = dict(files)

    def file_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.files))

    def read_bytes(self, relative_path: str) -> bytes:
        try:
            return self.files[relative_path]
        except KeyError as error:
            raise FileNotFoundError(relative_path) from error

    def read_json(self, relative_path: str) -> Any:
        return json.loads(self.read_bytes(relative_path).decode("utf-8"))

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.files


class InjectedBaseFault(BaseException):
    pass


@pytest.fixture(scope="module")
def rendered_run(tmp_path_factory: pytest.TempPathFactory) -> RenderedConfigureRun:
    root = tmp_path_factory.mktemp("run-manifest")
    package = assemble_package(
        compile_package(audited_request(root, "ShadowPriest"))
    )
    return render_configure_run_model(
        create_configure_run_model(
            package=package,
            stage_artifacts={
                "01_manifest/input.json": b'{"stage":1}\n',
                "02_source_documents/source.json": b'{"stage":2}\n',
                "03_research/research.json": b'{"stage":3}\n',
            },
        )
    )


def _files(rendered: RenderedConfigureRun) -> dict[str, bytes]:
    return {
        artifact.relative_path: artifact.content
        for artifact in rendered.artifacts
    }


def _replace_manifest_payload(
    files: dict[str, bytes],
    mutate: Callable[[dict[str, Any]], None],
) -> dict[str, bytes]:
    changed = dict(files)
    payload = json.loads(changed["package_manifest.json"])
    mutate(payload)
    changed["package_manifest.json"] = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    return changed


def _with_manifested_file(
    rendered: RenderedConfigureRun,
    *,
    paths: tuple[str, ...],
) -> dict[str, bytes]:
    files = _files(rendered)
    payload = json.loads(files["package_manifest.json"])
    for path in paths:
        content = f"content:{path}".encode("utf-8")
        files[path] = content
        payload["entries"].append(
            {
                "relative_path": path,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    payload["entries"].sort(key=lambda row: row["relative_path"])
    records = b"".join(
        (
            f"{row['relative_path']}\0{row['size']}\0"
            f"{row['sha256']}\n"
        ).encode("utf-8")
        for row in payload["entries"]
    )
    payload["content_root_sha256"] = hashlib.sha256(records).hexdigest()
    files["package_manifest.json"] = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    return files


def _rewrite_manifested_file(
    rendered: RenderedConfigureRun,
    *,
    path: str,
    content: bytes,
) -> dict[str, bytes]:
    files = _files(rendered)
    files[path] = content
    payload = json.loads(files["package_manifest.json"])
    entry = next(
        row for row in payload["entries"] if row["relative_path"] == path
    )
    entry["size"] = len(content)
    entry["sha256"] = hashlib.sha256(content).hexdigest()
    records = b"".join(
        (
            f"{row['relative_path']}\0{row['size']}\0"
            f"{row['sha256']}\n"
        ).encode("utf-8")
        for row in payload["entries"]
    )
    payload["content_root_sha256"] = hashlib.sha256(records).hexdigest()
    files["package_manifest.json"] = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    return files


def test_manifest_bytes_and_content_root_are_exact_and_deterministic() -> None:
    manifest = TreeManifest(
        schema_version=1,
        deck_name="Deck",
        deck_fingerprint="f" * 64,
        entries=(
            ManifestEntry(
                relative_path="a.txt",
                size=1,
                sha256=(
                    "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9"
                    "807785afee48bb"
                ),
            ),
            ManifestEntry(
                relative_path="stage/b.bin",
                size=2,
                sha256=(
                    "1e0bbd6c686ba050b8eb03ffeedc64fdc9d80947fce821abb"
                    "e5d6dc8d252c5ac"
                ),
            ),
        ),
        content_root_sha256=(
            "4bdad88182eda524fbe215be1d675943d5e62ada78750fc961"
            "1e432488aff4e9"
        ),
    )

    expected = b"""{
  "content_root_sha256": "4bdad88182eda524fbe215be1d675943d5e62ada78750fc9611e432488aff4e9",
  "deck_fingerprint": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
  "deck_name": "Deck",
  "entries": [
    {
      "relative_path": "a.txt",
      "sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
      "size": 1
    },
    {
      "relative_path": "stage/b.bin",
      "sha256": "1e0bbd6c686ba050b8eb03ffeedc64fdc9d80947fce821abbe5d6dc8d252c5ac",
      "size": 2
    }
  ],
  "schema_version": 1
}
"""

    assert write_tree_manifest(manifest) == expected
    assert write_tree_manifest(manifest) == write_tree_manifest(manifest)


@pytest.mark.parametrize(
    "path",
    (
        "PACKAGE_MANIFEST.JSON",
        "package_manifest.json/child",
        "PACKAGE_MANIFEST.JSON/child",
    ),
)
def test_manifest_entry_rejects_root_manifest_aliases_and_descendants(
    path: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="run_manifest_self_entry_forbidden",
    ):
        ManifestEntry(
            relative_path=path,
            size=0,
            sha256=hashlib.sha256(b"").hexdigest(),
        )


@pytest.mark.parametrize(
    "limit_name",
    (
        "MAX_MANIFEST_BYTES",
        "MAX_RUN_FILES",
        "MAX_RUN_TOTAL_BYTES",
    ),
)
def test_manifest_resource_bounds_accept_exact_and_reject_one_over(
    rendered_run: RenderedConfigureRun,
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
) -> None:
    files = _files(rendered_run)
    exact = {
        "MAX_MANIFEST_BYTES": len(files["package_manifest.json"]),
        "MAX_RUN_FILES": len(files),
        "MAX_RUN_TOTAL_BYTES": sum(
            len(content) for content in files.values()
        ),
    }[limit_name]
    monkeypatch.setattr(run_manifest, limit_name, exact)

    assert verify_tree_manifest(MemoryPackageView(files))

    monkeypatch.setattr(run_manifest, limit_name, exact - 1)
    with pytest.raises(ValueError, match="^run_manifest_invalid$"):
        verify_tree_manifest(MemoryPackageView(files))


def test_file_limit_includes_manifest_at_model_builder_and_verifier_boundaries(
    rendered_run: RenderedConfigureRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = build_tree_manifest(rendered_run)
    files = _files(rendered_run)
    physical_count = len(files)
    assert len(baseline.entries) == physical_count - 1
    monkeypatch.setattr(
        run_manifest,
        "MAX_RUN_FILES",
        physical_count,
    )

    assert TreeManifest(
        schema_version=baseline.schema_version,
        deck_name=baseline.deck_name,
        deck_fingerprint=baseline.deck_fingerprint,
        entries=baseline.entries,
        content_root_sha256=baseline.content_root_sha256,
    ) == baseline
    assert build_tree_manifest(rendered_run) == baseline
    assert verify_tree_manifest(MemoryPackageView(files)) == baseline

    monkeypatch.setattr(
        run_manifest,
        "MAX_RUN_FILES",
        physical_count - 1,
    )
    with pytest.raises(ValueError):
        TreeManifest(
            schema_version=baseline.schema_version,
            deck_name=baseline.deck_name,
            deck_fingerprint=baseline.deck_fingerprint,
            entries=baseline.entries,
            content_root_sha256=baseline.content_root_sha256,
        )
    with pytest.raises(ValueError):
        build_tree_manifest(rendered_run)
    with pytest.raises(ValueError, match="^run_manifest_invalid$"):
        verify_tree_manifest(MemoryPackageView(files))


def test_rendered_manifest_covers_every_other_artifact_in_stable_order(
    rendered_run: RenderedConfigureRun,
) -> None:
    manifest = build_tree_manifest(rendered_run)
    artifact_paths = tuple(
        artifact.relative_path
        for artifact in rendered_run.artifacts
        if artifact.relative_path != "package_manifest.json"
    )

    assert tuple(entry.relative_path for entry in manifest.entries) == (
        artifact_paths
    )
    assert tuple(entry.relative_path for entry in manifest.entries) == tuple(
        sorted(entry.relative_path for entry in manifest.entries)
    )
    assert "package_manifest.json" not in artifact_paths
    assert manifest.content_root_sha256 == rendered_run.content_root_sha256
    assert _files(rendered_run)["package_manifest.json"] == (
        write_tree_manifest(manifest)
    )


def test_verify_tree_manifest_accepts_exact_rendered_tree(
    rendered_run: RenderedConfigureRun,
) -> None:
    verified = verify_tree_manifest(MemoryPackageView(_files(rendered_run)))

    assert verified == build_tree_manifest(rendered_run)


def test_verify_tree_manifest_binds_configure_summary_identity(
    rendered_run: RenderedConfigureRun,
) -> None:
    summary = json.loads(_files(rendered_run)["configure_summary.json"])
    summary["deck_name"] = "OtherDeck"
    changed = _rewrite_manifested_file(
        rendered_run,
        path="configure_summary.json",
        content=(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        ),
    )

    with pytest.raises(ValueError, match="^run_manifest_invalid$"):
        verify_tree_manifest(MemoryPackageView(changed))


@pytest.mark.parametrize(
    "mutation",
    ("extra", "missing", "missing_manifest", "tamper", "zero_byte"),
)
def test_verify_tree_manifest_rejects_tree_membership_or_content_changes(
    rendered_run: RenderedConfigureRun,
    mutation: str,
) -> None:
    files = _files(rendered_run)
    if mutation == "extra":
        files["unexpected.txt"] = b"extra"
    elif mutation == "missing_manifest":
        del files["package_manifest.json"]
    elif mutation == "missing":
        path = next(
            path
            for path in files
            if path not in {"package_manifest.json", "configure_summary.json"}
        )
        del files[path]
    elif mutation == "tamper":
        path = next(
            path
            for path in files
            if path != "package_manifest.json"
        )
        files[path] = files[path][:-1] + bytes([files[path][-1] ^ 1])
    else:
        path = next(
            path
            for path in files
            if path != "package_manifest.json" and files[path]
        )
        files[path] = b""

    with pytest.raises(ValueError, match="^run_manifest_invalid$"):
        verify_tree_manifest(MemoryPackageView(files))


@pytest.mark.parametrize(
    "mutation",
    (
        "schema",
        "schema_bool",
        "unknown_root_key",
        "unknown_entry_key",
        "entries_type",
        "entry_type",
        "deck_name",
        "deck_fingerprint",
        "duplicate_path",
        "unsorted",
        "self_entry",
        "unsafe_path",
        "size",
        "size_bool",
        "sha256",
        "content_root",
    ),
)
def test_verify_tree_manifest_rejects_invalid_schema_and_identity(
    rendered_run: RenderedConfigureRun,
    mutation: str,
) -> None:
    def mutate(payload: dict[str, Any]) -> None:
        if mutation == "schema":
            payload["schema_version"] = 2
        elif mutation == "schema_bool":
            payload["schema_version"] = True
        elif mutation == "unknown_root_key":
            payload["unknown"] = None
        elif mutation == "unknown_entry_key":
            payload["entries"][0]["unknown"] = None
        elif mutation == "entries_type":
            payload["entries"] = {}
        elif mutation == "entry_type":
            payload["entries"][0] = []
        elif mutation == "deck_name":
            payload["deck_name"] = "OtherDeck"
        elif mutation == "deck_fingerprint":
            payload["deck_fingerprint"] = "0" * 64
        elif mutation == "duplicate_path":
            payload["entries"].append(dict(payload["entries"][0]))
        elif mutation == "unsorted":
            payload["entries"].reverse()
        elif mutation == "self_entry":
            payload["entries"].append(
                {
                    "relative_path": "package_manifest.json",
                    "size": 0,
                    "sha256": hashlib.sha256(b"").hexdigest(),
                }
            )
            payload["entries"].sort(
                key=lambda row: row["relative_path"]
            )
        elif mutation == "unsafe_path":
            payload["entries"][0]["relative_path"] = "../escape"
        elif mutation == "size":
            payload["entries"][0]["size"] += 1
        elif mutation == "size_bool":
            payload["entries"][0]["size"] = True
        elif mutation == "sha256":
            payload["entries"][0]["sha256"] = "0" * 64
        else:
            payload["content_root_sha256"] = "0" * 64

    changed = _replace_manifest_payload(_files(rendered_run), mutate)

    with pytest.raises(ValueError, match="^run_manifest_invalid$"):
        verify_tree_manifest(MemoryPackageView(changed))


@pytest.mark.parametrize(
    "encoding",
    ("compact", "bom", "crlf", "duplicate_key"),
)
def test_verify_tree_manifest_rejects_noncanonical_manifest_bytes(
    rendered_run: RenderedConfigureRun,
    encoding: str,
) -> None:
    files = _files(rendered_run)
    payload = json.loads(files["package_manifest.json"])
    if encoding == "compact":
        manifest_bytes = json.dumps(payload).encode("utf-8")
    elif encoding == "bom":
        manifest_bytes = b"\xef\xbb\xbf" + files["package_manifest.json"]
    elif encoding == "crlf":
        manifest_bytes = files["package_manifest.json"].replace(
            b"\n",
            b"\r\n",
        )
    else:
        manifest_bytes = files["package_manifest.json"].replace(
            b"{\n",
            b'{\n  "schema_version": 1,\n',
            1,
        )
    files["package_manifest.json"] = manifest_bytes

    with pytest.raises(ValueError, match="^run_manifest_invalid$"):
        verify_tree_manifest(MemoryPackageView(files))


def test_verify_tree_manifest_normalizes_io_errors_but_not_base_exceptions(
    rendered_run: RenderedConfigureRun,
) -> None:
    class FailingView(MemoryPackageView):
        def __init__(self, files: dict[str, bytes], error: BaseException):
            super().__init__(files)
            self.error = error

        def read_bytes(self, relative_path: str) -> bytes:
            if relative_path == "package_manifest.json":
                raise self.error
            return super().read_bytes(relative_path)

    with pytest.raises(ValueError, match="^run_manifest_invalid$"):
        verify_tree_manifest(
            FailingView(_files(rendered_run), OSError("read failed"))
        )
    with pytest.raises(InjectedBaseFault, match="interrupt"):
        verify_tree_manifest(
            FailingView(
                _files(rendered_run),
                InjectedBaseFault("interrupt"),
            )
        )


@pytest.mark.parametrize(
    "paths",
    (
        ("CONFIGURE_SUMMARY.JSON",),
        ("A", "a/b"),
        ("Dir/a.json", "dir/b.json"),
        ("a/x.json", "A/y/z.json"),
        ("04_PACKAGE/evil.json",),
        ("CON.json",),
        ("trailing.",),
        ("trailing ",),
        ("control\nname.json",),
        ("e\u0301.json",),
        ("x" * 4097,),
        ("../escape",),
        ("back\\slash.json",),
        ("illegal?.json",),
        ("illegal*.json",),
        ('illegal".json',),
        ("illegal<.json",),
        ("illegal>.json",),
        ("illegal|.json",),
    ),
    ids=(
        "casefold_collision",
        "casefold_ancestor",
        "directory_sibling_casefold",
        "directory_nested_casefold",
        "package_directory_casefold",
        "windows_device",
        "windows_trailing_dot",
        "windows_trailing_space",
        "control_character",
        "unicode_not_nfc",
        "oversized_path",
        "parent_escape",
        "backslash",
        "question_mark",
        "asterisk",
        "double_quote",
        "less_than",
        "greater_than",
        "pipe",
    ),
)
def test_verify_tree_manifest_rejects_ambiguous_physical_paths(
    rendered_run: RenderedConfigureRun,
    paths: tuple[str, ...],
) -> None:
    files = _with_manifested_file(rendered_run, paths=paths)

    with pytest.raises(ValueError, match="^run_manifest_invalid$"):
        verify_tree_manifest(MemoryPackageView(files))


def test_nested_manifest_filename_is_not_the_reserved_root_manifest(
    rendered_run: RenderedConfigureRun,
) -> None:
    files = _with_manifested_file(
        rendered_run,
        paths=("notes/package_manifest.json",),
    )

    manifest = verify_tree_manifest(MemoryPackageView(files))

    assert "notes/package_manifest.json" in {
        entry.relative_path for entry in manifest.entries
    }
