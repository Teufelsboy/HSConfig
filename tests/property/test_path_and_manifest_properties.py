from __future__ import annotations

import json
from pathlib import Path
import tempfile

import pytest
from hypothesis import given, settings, strategies as st

from hsconfig.package_domain import canonical_relative_path
from hsconfig.package_model import (
    DirectoryPackageView,
    PackageArtifact,
    _verify_package_view_manifest,
    content_root_sha256,
)


UNICODE_CONFUSABLE_SEPARATORS = (
    "\u2215",  # division slash
    "\u2044",  # fraction slash
    "\u29f5",  # reverse solidus operator
    "\u29f8",  # big solidus
    "\uff0f",  # fullwidth solidus
    "\ufe68",  # small reverse solidus
    "\uff3c",  # fullwidth reverse solidus
)

UNSAFE_PATH_FORMS = (
    "..",
    "../escape.json",
    "safe/../escape.json",
    "safe//child.json",
    "safe///child.json",
    "safe\\child.json",
    "/absolute.json",
    "//absolute.json",
    "C:/drive-qualified.json",
    "C:\\drive-qualified.json",
    "safe:colon.json",
)


@settings(max_examples=len(UNSAFE_PATH_FORMS), derandomize=True)
@given(path=st.sampled_from(UNSAFE_PATH_FORMS))
def test_canonical_relative_path_rejects_all_traversal_and_native_path_forms(
    path: str,
) -> None:
    """Break caught: a native, absolute, empty, or traversal component is accepted."""
    with pytest.raises(ValueError, match="^runtime_surface_path_invalid$"):
        canonical_relative_path(path)


@settings(max_examples=12, derandomize=True)
@given(separator=st.sampled_from(UNICODE_CONFUSABLE_SEPARATORS))
def test_canonical_relative_path_rejects_unicode_confusable_separators(
    separator: str,
) -> None:
    """Break caught: a lookalike separator can bypass path-component checks."""
    with pytest.raises(ValueError, match="^runtime_surface_path_invalid$"):
        canonical_relative_path(f"safe{separator}child.json")


@settings(max_examples=12, derandomize=True)
@given(tamper=st.binary(min_size=1, max_size=24).filter(lambda value: value != b"{}"))
def test_manifest_tampering_is_always_detected(tamper: bytes) -> None:
    """Break caught: modified package bytes still satisfy the persisted manifest."""
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        artifact = PackageArtifact.from_content(
            relative_path="reports/payload.json",
            content=b"{}",
        )
        target = root / artifact.relative_path
        target.parent.mkdir(parents=True)
        target.write_bytes(artifact.content)
        manifest = {
            "artifacts": [
                {
                    "relative_path": artifact.relative_path,
                    "size": artifact.size,
                    "sha256": artifact.sha256,
                }
            ],
            "content_root_sha256": content_root_sha256((artifact,)),
        }
        manifest_path = root / "reports/package_manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        target.write_bytes(tamper)

        with pytest.raises(ValueError, match="typed_package_manifest_mismatch"):
            _verify_package_view_manifest(DirectoryPackageView(root))
