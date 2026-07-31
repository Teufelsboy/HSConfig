from __future__ import annotations

import json
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
