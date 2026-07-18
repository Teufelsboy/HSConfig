from __future__ import annotations

from scripts.check_hsconfig_currentness import (
    parse_ahead_behind,
    parse_status_short,
)


def test_parse_clean_branch_status() -> None:
    branch, dirty = parse_status_short("## codex/hsconfig-canonical-source-status-sync\n")

    assert branch == "codex/hsconfig-canonical-source-status-sync"
    assert dirty is False


def test_parse_dirty_branch_status() -> None:
    branch, dirty = parse_status_short(
        "## codex/hsconfig-canonical-source-status-sync\n"
        " M src/hsconfig/source_candidate_registry.py\n"
    )

    assert branch == "codex/hsconfig-canonical-source-status-sync"
    assert dirty is True


def test_parse_ahead_behind_counts() -> None:
    assert parse_ahead_behind("54\t0\n") == (54, 0)
    assert parse_ahead_behind("0 2\n") == (0, 2)
