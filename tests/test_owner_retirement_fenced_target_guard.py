from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import pytest

from hsconfig import runtime_installer
from hsconfig.package_io import path_identity
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionJournal,
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from tests.test_configure_prepublication_apply import _file_fingerprint, _physical_tree
from tests.test_runtime_installer import (
    _exercise_candidate_bound_prefix,
    _write_task9_finalized_retention,
)


def _fenced_stale_owner_before_final_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    Mapping[str, Any],
    Path,
    Mapping[str, tuple[int, int, int]],
    RuntimeTransactionJournal,
    Path,
    Path,
]:
    result = _exercise_candidate_bound_prefix(
        tmp_path,
        monkeypatch,
        through_owner_bind=True,
        through_committed=True,
        seed_stale_owned_revision=True,
        stop_before_action="finalize_attempt_record",
    )
    recovery = result.recovery
    assert recovery["expected_action"] == "finalize_attempt_record"
    runtime_root = result.fixture.pipeline.runtime_root
    attempt_id = result.fixture.runtime_admission.apply_attempt_id
    owners = tuple(
        journal
        for journal in load_runtime_transaction_journals(runtime_root)
        if journal.owns_target and journal.transaction_id != attempt_id
    )
    assert len(owners) == 1
    owner = owners[0]
    target = runtime_root / owner.target_path
    assert target.is_dir()
    assert path_identity(target) == owner.target_identity
    owner_path = runtime_transaction_journal_path(runtime_root, owner.transaction_id)
    fence_path, _raw = _write_task9_finalized_retention(
        runtime_root,
        transaction_id=owner.transaction_id,
        retention_owner_run_id="d" * 32,
        journal=owner,
        target=target,
        owner=owner,
    )
    runtime_installer._commit_or_confirm_suffix_file(
        recovery,
        action="finalize_attempt_record",
    )
    layout = result.cursor.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    assert layout["stage"] == "COMPLETE"
    layout_identities = {
        str(row["role"]): tuple(row["successor_identity"])
        for row in layout["directories"]
    }
    return recovery, runtime_root, layout_identities, owner, owner_path, fence_path


def _drift_owned_target(runtime_root: Path, owner: RuntimeTransactionJournal) -> Path:
    target = runtime_root / owner.target_path
    victim = next(path for path in sorted(target.rglob("*")) if path.is_file())
    victim.write_bytes(victim.read_bytes() + b"\n")
    return target


def test_owner_retirement_skips_exact_fenced_drifted_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        recovery,
        runtime_root,
        layout_identities,
        owner,
        owner_path,
        fence_path,
    ) = _fenced_stale_owner_before_final_attempt(tmp_path, monkeypatch)
    target = _drift_owned_target(runtime_root, owner)
    target_identity = path_identity(target)
    tombstone = (
        runtime_root
        / ".hsconfig"
        / "owner-retirements"
        / f"{owner.transaction_id}.json"
    )
    before = {
        "owner": _file_fingerprint(owner_path),
        "fence": _file_fingerprint(fence_path),
        "target": _physical_tree(target),
    }

    cursor = runtime_installer._initial_owner_retirement_cursor(
        recovery=recovery,
        runtime_root=runtime_root,
        layout_identities=layout_identities,
    )

    assert cursor is None
    assert not os.path.lexists(tombstone)
    assert path_identity(target) == target_identity
    assert before == {
        "owner": _file_fingerprint(owner_path),
        "fence": _file_fingerprint(fence_path),
        "target": _physical_tree(target),
    }


@pytest.mark.parametrize("case", ("malformed_fence", "replaced_target", "no_fence"))
def test_owner_retirement_does_not_relax_invalid_or_unfenced_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    (
        recovery,
        runtime_root,
        layout_identities,
        owner,
        _owner_path,
        fence_path,
    ) = _fenced_stale_owner_before_final_attempt(tmp_path, monkeypatch)
    target = runtime_root / owner.target_path
    if case == "malformed_fence":
        fence_path.write_bytes(b"{}\n")
    elif case == "replaced_target":
        replacement = tmp_path / "escrow-target"
        target.rename(replacement)
        target.mkdir()
    else:
        fence_path.unlink()
        _drift_owned_target(runtime_root, owner)
    tombstone = (
        runtime_root
        / ".hsconfig"
        / "owner-retirements"
        / f"{owner.transaction_id}.json"
    )
    runtime_before = _physical_tree(runtime_root)

    with pytest.raises(
        ValueError,
        match=(
            "runtime_attempt_retention_store_invalid"
            if case == "malformed_fence"
            else "runtime_owner_retirement_initial_authority_invalid"
        ),
    ):
        runtime_installer._initial_owner_retirement_cursor(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
        )

    assert not os.path.lexists(tombstone)
    assert _physical_tree(runtime_root) == runtime_before
