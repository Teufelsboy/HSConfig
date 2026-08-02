from __future__ import annotations

from pathlib import Path
import tempfile

from hsconfig.output_publisher import publish_configure_run
from tests.test_output_publisher import build_rendered_run


def test_repeated_canonical_publication_is_idempotent() -> None:
    """Break caught: the same rendered authority changes a settled revision."""
    with tempfile.TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        rendered = build_rendered_run(
            root / "inputs",
            revision=1,
            fixture_paths=True,
        )
        destination = root / "published"

        first = publish_configure_run(rendered, destination)
        second = publish_configure_run(rendered, destination)

        assert second.revision_root == first.revision_root
        assert second.reused_existing_revision is True
        assert second.content_root_sha256 == rendered.content_root_sha256
