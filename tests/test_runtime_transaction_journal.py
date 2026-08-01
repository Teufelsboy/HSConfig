from __future__ import annotations

import json
import multiprocessing
import os
from dataclasses import replace
from pathlib import Path

import pytest

from hsconfig.runtime_transaction_journal import (
    MAX_RUNTIME_TRANSACTION_FILES,
    RuntimeTransactionJournal,
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    read_runtime_transaction_journal,
    runtime_transaction_journal_bytes,
    write_runtime_transaction_journal,
)


def journal_fixture(**overrides: object) -> RuntimeTransactionJournal:
    transaction_id = "1" * 32
    digest = "a" * 64
    values: dict[str, object] = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "deck_name": "ShadowPriest",
        "source_manifest_sha256": "b" * 64,
        "state_key": f"shadowpriest--sha256-{'c' * 64}",
        "logical_config_dir": "shadowpriest",
        "package_root_sha256": digest,
        "candidate_path": f".hsconfig/staging/{transaction_id}",
        "target_path": f"CustomConfig/shadowpriest--sha256-{digest}",
        "candidate_identity": (7, 8, 0o40700),
        "target_identity": None,
        "owns_target": False,
        "previous_config_dir": "shadowpriest--sha256-" + "d" * 64,
        "next_config_dir": f"shadowpriest--sha256-{digest}",
        "previous_ini_sha256": "e" * 64,
        "next_ini_sha256": "f" * 64,
        "phase": RuntimeTransactionPhase.RUNTIME_VERIFIED,
    }
    values.update(overrides)
    return RuntimeTransactionJournal(**values)  # type: ignore[arg-type]


def _journal_write_hard_exit_worker(
    path: Path,
    journal: RuntimeTransactionJournal,
    stage: str,
) -> None:
    def terminate(observed: str) -> None:
        if observed == stage:
            os._exit(77)

    write_runtime_transaction_journal(path, journal, fault_hook=terminate)


def test_journal_is_strict_canonical_and_round_trips(tmp_path: Path) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    journal = journal_fixture()
    path = transactions / f"{journal.transaction_id}.json"

    write_runtime_transaction_journal(path, journal)

    assert read_runtime_transaction_journal(path) == journal
    assert path.read_bytes() == runtime_transaction_journal_bytes(journal)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert list(payload) == sorted(payload)
    assert payload["candidate_identity"] == [7, 8, 0o40700]
    assert load_runtime_transaction_journals(tmp_path) == (journal,)


@pytest.mark.parametrize(
    "stage",
    (
        "before_temp_write",
        "after_temp_write",
        "after_temp_flush",
        "before_replace",
        "after_replace",
        "after_parent_flush",
    ),
)
def test_hard_kill_during_journal_update_recovers_old_or_new_canonical_state(
    tmp_path: Path,
    stage: str,
) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    old = journal_fixture()
    new = replace(
        old,
        target_identity=old.candidate_identity,
        owns_target=True,
        phase=RuntimeTransactionPhase.FINALIZED,
    )
    path = transactions / f"{old.transaction_id}.json"
    write_runtime_transaction_journal(path, old)

    process = multiprocessing.get_context("spawn").Process(
        target=_journal_write_hard_exit_worker,
        args=(path, new, stage),
    )
    process.start()
    process.join(60)
    if process.is_alive():
        process.kill()
        process.join(10)
        pytest.fail(f"journal worker hung at {stage}")
    assert process.exitcode == 77

    recovered = load_runtime_transaction_journals(tmp_path)
    if stage in {
        "before_temp_write",
        "after_temp_write",
        "after_temp_flush",
        "before_replace",
    }:
        assert recovered in {(old,), (new,)}
    else:
        assert recovered == (new,)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"candidate_path": "CustomConfig/candidate"},
            "runtime_transaction_journal_invalid",
        ),
        (
            {"target_path": "../outside"},
            "runtime_transaction_journal_invalid",
        ),
        (
            {"next_config_dir": "shadowpriest"},
            "runtime_transaction_journal_invalid",
        ),
        (
            {
                "phase": RuntimeTransactionPhase.INI_COMMITTED,
                "target_identity": None,
            },
            "runtime_transaction_journal_invalid",
        ),
        (
            {"owns_target": True, "target_identity": None},
            "runtime_transaction_journal_invalid",
        ),
    ],
)
def test_journal_rejects_path_phase_and_identity_ambiguity(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        journal_fixture(**overrides)


def test_journal_rejects_noncanonical_and_damaged_bytes(tmp_path: Path) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    journal = journal_fixture()
    path = transactions / f"{journal.transaction_id}.json"
    canonical = runtime_transaction_journal_bytes(journal)
    path.write_bytes(canonical.replace(b"  ", b" ", 1))

    with pytest.raises(ValueError, match="runtime_transaction_journal_invalid"):
        read_runtime_transaction_journal(path)


def test_journal_loader_fails_closed_on_unknown_entry(tmp_path: Path) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    (transactions / "README.txt").write_text("unknown", encoding="utf-8")

    with pytest.raises(ValueError, match="runtime_transaction_store_invalid"):
        load_runtime_transaction_journals(tmp_path)


def test_journal_loader_ignores_truncated_pending_without_mutating_it(
    tmp_path: Path,
) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    journal = journal_fixture()
    path = transactions / f"{journal.transaction_id}.json"
    pending = transactions / (
        f".{journal.transaction_id}.json.{'2' * 32}.tmp"
    )
    write_runtime_transaction_journal(path, journal)
    pending.write_bytes(b"{\n")
    before = pending.read_bytes()
    before_status = pending.stat()
    before_identity = (
        before_status.st_dev,
        before_status.st_ino,
        before_status.st_mode,
    )

    assert load_runtime_transaction_journals(tmp_path) == (journal,)

    assert path.is_file()
    assert pending.read_bytes() == before
    after_status = pending.stat()
    assert (
        after_status.st_dev,
        after_status.st_ino,
        after_status.st_mode,
    ) == before_identity


def test_journal_loader_rejects_non_monotonic_final_pending_pair(
    tmp_path: Path,
) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    journal = journal_fixture()
    path = transactions / f"{journal.transaction_id}.json"
    pending = transactions / (
        f".{journal.transaction_id}.json.{'2' * 32}.tmp"
    )
    write_runtime_transaction_journal(path, journal)
    conflicting = replace(journal, deck_name="OtherDeck")
    pending.write_bytes(runtime_transaction_journal_bytes(conflicting))
    before = pending.read_bytes()

    with pytest.raises(ValueError, match="runtime_transaction_store_invalid"):
        load_runtime_transaction_journals(tmp_path)

    assert path.is_file()
    assert pending.read_bytes() == before


def test_journal_loader_ignores_truncated_pending_without_final(
    tmp_path: Path,
) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    transaction_id = "1" * 32
    pending = transactions / f".{transaction_id}.json.{'2' * 32}.tmp"
    pending.write_bytes(b"")
    before_status = pending.stat()

    assert load_runtime_transaction_journals(tmp_path) == ()

    after_status = pending.stat()
    assert pending.read_bytes() == b""
    assert (after_status.st_dev, after_status.st_ino, after_status.st_mode) == (
        before_status.st_dev,
        before_status.st_ino,
        before_status.st_mode,
    )


def test_truncated_reserved_temp_does_not_block_later_journal_update(
    tmp_path: Path,
) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    old = journal_fixture()
    new = replace(
        old,
        target_identity=old.candidate_identity,
        owns_target=True,
        phase=RuntimeTransactionPhase.FINALIZED,
    )
    path = transactions / f"{old.transaction_id}.json"
    truncated = transactions / (
        f".{old.transaction_id}.json.{'2' * 32}.tmp"
    )
    write_runtime_transaction_journal(path, old)
    truncated.write_bytes(b"{\n")
    before_status = truncated.stat()
    before = truncated.read_bytes()

    write_runtime_transaction_journal(path, new)

    assert load_runtime_transaction_journals(tmp_path) == (new,)
    after_status = truncated.stat()
    assert truncated.read_bytes() == before
    assert (
        after_status.st_dev,
        after_status.st_ino,
        after_status.st_mode,
    ) == (
        before_status.st_dev,
        before_status.st_ino,
        before_status.st_mode,
    )


def test_journal_loader_rejects_hardlinked_journal(tmp_path: Path) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    journal = journal_fixture()
    path = transactions / f"{journal.transaction_id}.json"
    write_runtime_transaction_journal(path, journal)
    alias = tmp_path / "alias.json"
    try:
        os.link(path, alias)
    except OSError as error:
        pytest.skip(f"hard links unavailable: {error}")

    with pytest.raises(ValueError, match="runtime_transaction_journal_invalid"):
        read_runtime_transaction_journal(path)


def test_journal_loader_rejects_reparse_journal(tmp_path: Path) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    journal = journal_fixture()
    outside = tmp_path / "outside.json"
    outside.write_bytes(runtime_transaction_journal_bytes(journal))
    alias = transactions / f"{journal.transaction_id}.json"
    try:
        os.symlink(outside, alias)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    with pytest.raises(ValueError, match="runtime_transaction_store_invalid"):
        load_runtime_transaction_journals(tmp_path)


def test_journal_store_enforces_bounded_file_count(tmp_path: Path) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    for index in range(MAX_RUNTIME_TRANSACTION_FILES + 1):
        (transactions / f"{index:032x}.json").write_bytes(b"{}\n")

    with pytest.raises(ValueError, match="runtime_transaction_store_invalid"):
        load_runtime_transaction_journals(tmp_path)


def test_finalized_owner_requires_matching_candidate_and_target_identity() -> None:
    with pytest.raises(
        ValueError,
        match="runtime_transaction_journal_invalid",
    ):
        replace(
            journal_fixture(),
            phase=RuntimeTransactionPhase.FINALIZED,
            target_identity=(7, 9, 0o40700),
            owns_target=True,
        )

    finalized = replace(
        journal_fixture(),
        phase=RuntimeTransactionPhase.FINALIZED,
        target_identity=(7, 8, 0o40700),
        owns_target=True,
    )
    assert finalized.owns_target is True
