from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile

from hypothesis import given, settings, strategies as st

from hsconfig.package_assembler import assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_render_authority import render_package_authority
from hsconfig.package_request import PackageResolutionSnapshot
from tests.helpers.audited_package_request import audited_request


def _render_authority(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    request = audited_request(root, "ShadowPriest", fixture_paths=True)
    return request, render_package_authority(assemble_package(compile_package(request)))


def _reordered_request(request, *, reverse: bool):
    preconfig = request.snapshot.general_preconfig.to_value()
    rows = tuple(preconfig.items())
    reordered_preconfig = dict(reversed(rows) if reverse else rows)
    snapshot = PackageResolutionSnapshot.from_strict(
        request.snapshot.strict_build_context,
        reordered_preconfig,
    )
    return replace(request, snapshot=snapshot)


def _artifact_bytes(rendered) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (artifact.relative_path, artifact.content)
        for artifact in rendered.artifacts.artifacts
    )


@settings(max_examples=2, deadline=None, derandomize=True)
@given(reverse=st.booleans())
def test_canonical_authority_is_byte_deterministic_for_equivalent_mapping_orders_and_roots(
    reverse: bool,
) -> None:
    """Break caught: mapping order or absolute source root leaks into authority bytes."""
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        first_request, first = _render_authority(root / "absolute-first")
        reordered = _reordered_request(first_request, reverse=reverse)
        same_root_order_variant = render_package_authority(
            assemble_package(compile_package(reordered))
        )
        _second_request, second_root = _render_authority(root / "absolute-second")

        assert _artifact_bytes(first) == _artifact_bytes(same_root_order_variant)
        assert first.content_root_sha256 == same_root_order_variant.content_root_sha256
        assert _artifact_bytes(first) == _artifact_bytes(second_root)
        assert first.content_root_sha256 == second_root.content_root_sha256
