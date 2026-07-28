from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from hsconfig.atomic_io import (
    atomic_write_bytes,
    atomic_write_json,
    flush_file,
)


FAULT_STAGES = (
    "before_temp_write",
    "after_temp_write",
    "after_temp_flush",
    "before_replace",
    "after_replace",
    "after_parent_flush",
)
PRE_REPLACE_STAGES = frozenset(FAULT_STAGES[:4])


class InjectedFault(RuntimeError):
    pass


def _fault_at(target_stage: str) -> Callable[[str], None]:
    def raise_at_stage(stage: str) -> None:
        if stage == target_stage:
            raise InjectedFault(stage)

    return raise_at_stage


@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_atomic_write_bytes_preserves_a_complete_version_at_every_fault_stage(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    target = tmp_path / "state.bin"
    old_content = b"old-state"
    new_content = b"new-state-with-a-different-length"
    target.write_bytes(old_content)

    with pytest.raises(InjectedFault, match=fault_stage):
        atomic_write_bytes(
            target,
            new_content,
            fault_hook=_fault_at(fault_stage),
        )

    if fault_stage in PRE_REPLACE_STAGES:
        assert target.read_bytes() == old_content
    else:
        assert target.read_bytes() in (old_content, new_content)
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_atomic_write_json_never_publishes_truncated_or_mixed_json(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    target = tmp_path / "state.json"
    old_payload = {"generation": "old", "values": [1, 2, 3]}
    new_payload = {
        "generation": "new",
        "values": ["different", "complete", "content"],
    }
    target.write_text(json.dumps(old_payload), encoding="utf-8")

    with pytest.raises(InjectedFault, match=fault_stage):
        atomic_write_json(
            target,
            new_payload,
            fault_hook=_fault_at(fault_stage),
        )

    published = json.loads(target.read_text(encoding="utf-8"))
    if fault_stage in PRE_REPLACE_STAGES:
        assert published == old_payload
    else:
        assert published in (old_payload, new_payload)
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_calls_the_six_fault_stages_in_commit_order(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.bin"
    observed_stages: list[str] = []

    atomic_write_bytes(target, b"complete", fault_hook=observed_stages.append)

    assert observed_stages == list(FAULT_STAGES)
    assert target.read_bytes() == b"complete"


def test_atomic_write_keeps_replacement_correct_when_parent_flush_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")

    def reject_directory_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
    ) -> int:
        raise OSError("directory handles are unavailable on this platform")

    monkeypatch.setattr(os, "open", reject_directory_open)

    atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [target]


def test_flush_file_flushes_an_existing_file_without_changing_its_bytes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.bin"
    content = b"bytes-that-must-not-change"
    target.write_bytes(content)

    flush_file(target)

    assert target.read_bytes() == content
