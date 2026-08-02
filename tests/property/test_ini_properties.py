from __future__ import annotations

from pathlib import Path
import tempfile

import pytest
from hypothesis import given, settings, strategies as st

from hsconfig.deck_config_ini import (
    read_deck_config,
    render_deck_config,
    replace_deck_config_if_unchanged,
)


@settings(max_examples=12, derandomize=True)
@given(
    before=st.text(alphabet="abéö☃", min_size=1, max_size=12),
    after=st.text(alphabet="xyüñ☂", min_size=1, max_size=12),
)
def test_ini_update_preserves_unrelated_bytes_and_never_overwrites_changed_file(
    before: str,
    after: str,
) -> None:
    """Break caught: a stale compare-and-swap overwrites concurrent INI bytes."""
    with tempfile.TemporaryDirectory() as raw_root:
        path = Path(raw_root) / "deck_config.ini"
        before_bytes = before.encode("utf-8")
        after_bytes = after.encode("utf-8")
        original = (
            b"; before="
            + before_bytes
            + b"\r\n[CONFIGS]\r\nDeck = Old\r\n[Other]\r\nvalue="
            + after_bytes
        )
        path.write_bytes(original)
        snapshot = read_deck_config(path, deck_name="Deck")
        rendered = render_deck_config(snapshot, deck_name="Deck", config_dir="New")

        assert rendered == original.replace(b"Deck = Old", b"Deck = New")
        assert b"; before=" + before_bytes in rendered
        assert b"value=" + after_bytes in rendered

        concurrent = original + b"\r\n; concurrent edit"
        path.write_bytes(concurrent)
        with pytest.raises(RuntimeError, match="deck_config_ini_concurrent_change"):
            replace_deck_config_if_unchanged(snapshot, rendered)
        assert path.read_bytes() == concurrent
