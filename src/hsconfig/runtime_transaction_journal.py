"""Strict crash-recovery journals for transactional runtime activation."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from hsconfig.atomic_io import FaultHook, atomic_write_bytes, no_fault
from hsconfig.package_io import (
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_plain_directory,
    status_is_reparse,
)
from hsconfig.run_manifest import canonical_run_relative_path


RUNTIME_TRANSACTION_SCHEMA_VERSION = 1
MAX_RUNTIME_TRANSACTION_FILES = 1024
MAX_RUNTIME_TRANSACTION_BYTES = 1024 * 1024
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STATE_KEY = re.compile(r"^[a-z0-9][a-z0-9-]*--sha256-[0-9a-f]{64}$")
_SAFE_COMPONENT_LIMIT = 255
_KEYS = frozenset(
    {
        "schema_version",
        "transaction_id",
        "deck_name",
        "source_manifest_sha256",
        "state_key",
        "logical_config_dir",
        "package_root_sha256",
        "candidate_path",
        "target_path",
        "candidate_identity",
        "target_identity",
        "owns_target",
        "previous_config_dir",
        "next_config_dir",
        "previous_ini_sha256",
        "next_ini_sha256",
        "phase",
        "cleanup_started",
        "cleanup_entries",
        "cleanup_cursor",
    }
)
_CLEANUP_ENTRY_KEYS = frozenset({"kind", "relative_path", "identity"})


class RuntimeTransactionPhase(StrEnum):
    PREPARED = "prepared"
    RUNTIME_STAGED = "runtime_staged"
    RUNTIME_VERIFIED = "runtime_verified"
    INI_COMMITTED = "ini_committed"
    STATE_COMMITTED = "state_committed"
    FINALIZED = "finalized"


@dataclass(frozen=True, slots=True)
class RuntimeCleanupEntry:
    kind: str
    relative_path: str
    identity: tuple[int, int, int]

    def __post_init__(self) -> None:
        try:
            canonical = canonical_run_relative_path(self.relative_path)
        except (TypeError, ValueError) as error:
            raise ValueError("runtime_cleanup_entry_invalid") from error
        if (
            self.kind not in {"file", "directory"}
            or canonical != self.relative_path
            or not _valid_identity(self.identity)
        ):
            raise ValueError("runtime_cleanup_entry_invalid")


@dataclass(frozen=True, slots=True)
class RuntimeTransactionJournal:
    schema_version: int
    transaction_id: str
    deck_name: str
    source_manifest_sha256: str
    state_key: str
    logical_config_dir: str
    package_root_sha256: str
    candidate_path: str
    target_path: str
    candidate_identity: tuple[int, int, int] | None
    target_identity: tuple[int, int, int] | None
    owns_target: bool
    previous_config_dir: str | None
    next_config_dir: str
    previous_ini_sha256: str | None
    next_ini_sha256: str
    phase: RuntimeTransactionPhase
    cleanup_started: bool = False
    cleanup_entries: tuple[RuntimeCleanupEntry, ...] = ()
    cleanup_cursor: int = 0

    def __post_init__(self) -> None:
        expected_next = (
            f"{self.logical_config_dir}--sha256-{self.package_root_sha256}"
        )
        candidate_with_identity = self.candidate_identity is not None
        target_with_identity = self.target_identity is not None
        committed = self.phase in {
            RuntimeTransactionPhase.INI_COMMITTED,
            RuntimeTransactionPhase.STATE_COMMITTED,
            RuntimeTransactionPhase.FINALIZED,
        }
        if (
            type(self.schema_version) is not int
            or self.schema_version != RUNTIME_TRANSACTION_SCHEMA_VERSION
            or not isinstance(self.transaction_id, str)
            or not _TRANSACTION_ID.fullmatch(self.transaction_id)
            or not _valid_deck_name(self.deck_name)
            or not _SHA256.fullmatch(self.source_manifest_sha256)
            or not _STATE_KEY.fullmatch(self.state_key)
            or len(self.state_key) > _SAFE_COMPONENT_LIMIT
            or not _valid_component(self.logical_config_dir)
            or not _SHA256.fullmatch(self.package_root_sha256)
            or self.next_config_dir != expected_next
            or not _valid_component(self.next_config_dir)
            or self.candidate_path
            != f".hsconfig/staging/{self.transaction_id}"
            or self.target_path != f"CustomConfig/{self.next_config_dir}"
            or not _valid_identity(self.candidate_identity)
            or not _valid_identity(self.target_identity)
            or type(self.owns_target) is not bool
            or (
                self.previous_config_dir is not None
                and not _valid_component(self.previous_config_dir)
            )
            or (
                self.previous_ini_sha256 is not None
                and not _SHA256.fullmatch(self.previous_ini_sha256)
            )
            or not _SHA256.fullmatch(self.next_ini_sha256)
            or not isinstance(self.phase, RuntimeTransactionPhase)
            or type(self.cleanup_started) is not bool
            or not isinstance(self.cleanup_entries, tuple)
            or any(
                not isinstance(entry, RuntimeCleanupEntry)
                for entry in self.cleanup_entries
            )
            or len(
                {entry.relative_path for entry in self.cleanup_entries}
            )
            != len(self.cleanup_entries)
            or type(self.cleanup_cursor) is not int
            or not 0 <= self.cleanup_cursor <= len(self.cleanup_entries)
            or (
                self.cleanup_started
                and (
                    self.phase != RuntimeTransactionPhase.FINALIZED
                    or not self.owns_target
                )
            )
            or (
                not self.cleanup_started
                and (self.cleanup_entries or self.cleanup_cursor != 0)
            )
            or (
                self.phase
                in {
                    RuntimeTransactionPhase.RUNTIME_STAGED,
                    RuntimeTransactionPhase.RUNTIME_VERIFIED,
                }
                and not candidate_with_identity
            )
            or (committed and not target_with_identity)
            or (
                target_with_identity
                and self.phase
                in {
                    RuntimeTransactionPhase.PREPARED,
                    RuntimeTransactionPhase.RUNTIME_STAGED,
                }
            )
            or (self.owns_target and not target_with_identity)
            or (
                self.owns_target
                and self.phase
                in {
                    RuntimeTransactionPhase.PREPARED,
                    RuntimeTransactionPhase.RUNTIME_STAGED,
                }
            )
            or (
                self.owns_target
                and self.candidate_identity != self.target_identity
            )
        ):
            raise ValueError("runtime_transaction_journal_invalid")


def runtime_transaction_journal_bytes(
    journal: RuntimeTransactionJournal,
) -> bytes:
    if not isinstance(journal, RuntimeTransactionJournal):
        raise TypeError("runtime_transaction_journal_required")
    payload = asdict(journal)
    payload["phase"] = journal.phase.value
    for key in ("candidate_identity", "target_identity"):
        identity = payload[key]
        payload[key] = list(identity) if identity is not None else None
    content = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    if len(content) > MAX_RUNTIME_TRANSACTION_BYTES:
        raise ValueError("runtime_transaction_journal_too_large")
    return content


def runtime_transaction_journal_path(
    runtime_root: Path,
    transaction_id: str,
) -> Path:
    if not isinstance(transaction_id, str) or not _TRANSACTION_ID.fullmatch(
        transaction_id
    ):
        raise ValueError("runtime_transaction_journal_invalid")
    return (
        Path(runtime_root)
        / ".hsconfig"
        / "transactions"
        / f"{transaction_id}.json"
    )


def write_runtime_transaction_journal(
    path: Path,
    journal: RuntimeTransactionJournal,
    *,
    fault_hook: FaultHook = no_fault,
) -> None:
    target = Path(path)
    if (
        target.name != f"{journal.transaction_id}.json"
        or target.parent.name != "transactions"
        or target.parent.parent.name != ".hsconfig"
    ):
        raise ValueError("runtime_transaction_journal_invalid")
    atomic_write_bytes(
        target,
        runtime_transaction_journal_bytes(journal),
        fault_hook=fault_hook,
    )


def read_runtime_transaction_journal(
    path: Path,
) -> RuntimeTransactionJournal:
    target = Path(path)
    try:
        status = plain_file_status(target)
        content = read_file_no_follow(
            target,
            expected_status=status,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        payload = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        journal = _journal_from_payload(payload)
        if target.name != f"{journal.transaction_id}.json":
            raise ValueError("filename")
        if content != runtime_transaction_journal_bytes(journal):
            raise ValueError("noncanonical")
        return journal
    except Exception as error:
        raise ValueError("runtime_transaction_journal_invalid") from error


def load_runtime_transaction_journals(
    runtime_root: Path,
) -> tuple[RuntimeTransactionJournal, ...]:
    transactions = Path(runtime_root) / ".hsconfig" / "transactions"
    if not path_lexists(transactions):
        return ()
    try:
        require_plain_directory(transactions)
        entries: list[tuple[str, Path]] = []
        with os.scandir(transactions) as iterator:
            for entry in iterator:
                if len(entries) >= MAX_RUNTIME_TRANSACTION_FILES:
                    raise ValueError("bounds")
                status = Path(entry.path).lstat()
                if (
                    status_is_reparse(status)
                    or not stat.S_ISREG(status.st_mode)
                    or status.st_nlink != 1
                    or not re.fullmatch(r"[0-9a-f]{32}\.json", entry.name)
                ):
                    raise ValueError("entry")
                entries.append((entry.name, Path(entry.path)))
        journals = tuple(
            read_runtime_transaction_journal(path)
            for _name, path in sorted(entries)
        )
        transaction_ids = [journal.transaction_id for journal in journals]
        if len(transaction_ids) != len(set(transaction_ids)):
            raise ValueError("duplicate")
        return journals
    except Exception as error:
        raise ValueError("runtime_transaction_store_invalid") from error


def _journal_from_payload(payload: object) -> RuntimeTransactionJournal:
    if not isinstance(payload, dict) or frozenset(payload) != _KEYS:
        raise ValueError("schema")
    candidate_identity = _parse_identity(payload["candidate_identity"])
    target_identity = _parse_identity(payload["target_identity"])
    cleanup_rows = payload["cleanup_entries"]
    if not isinstance(cleanup_rows, list):
        raise ValueError("cleanup entries")
    cleanup_entries: list[RuntimeCleanupEntry] = []
    for row in cleanup_rows:
        if not isinstance(row, dict) or frozenset(row) != _CLEANUP_ENTRY_KEYS:
            raise ValueError("cleanup entry")
        identity = _parse_identity(row["identity"])
        if identity is None:
            raise ValueError("cleanup identity")
        cleanup_entries.append(
            RuntimeCleanupEntry(
                kind=row["kind"],
                relative_path=row["relative_path"],
                identity=identity,
            )
        )
    return RuntimeTransactionJournal(
        schema_version=payload["schema_version"],
        transaction_id=payload["transaction_id"],
        deck_name=payload["deck_name"],
        source_manifest_sha256=payload["source_manifest_sha256"],
        state_key=payload["state_key"],
        logical_config_dir=payload["logical_config_dir"],
        package_root_sha256=payload["package_root_sha256"],
        candidate_path=payload["candidate_path"],
        target_path=payload["target_path"],
        candidate_identity=candidate_identity,
        target_identity=target_identity,
        owns_target=payload["owns_target"],
        previous_config_dir=payload["previous_config_dir"],
        next_config_dir=payload["next_config_dir"],
        previous_ini_sha256=payload["previous_ini_sha256"],
        next_ini_sha256=payload["next_ini_sha256"],
        phase=RuntimeTransactionPhase(payload["phase"]),
        cleanup_started=payload["cleanup_started"],
        cleanup_entries=tuple(cleanup_entries),
        cleanup_cursor=payload["cleanup_cursor"],
    )


def _parse_identity(value: object) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(part) is not int or part < 0 for part in value)
    ):
        raise ValueError("identity")
    return value[0], value[1], value[2]


def _valid_identity(value: object) -> bool:
    return value is None or (
        isinstance(value, tuple)
        and len(value) == 3
        and all(type(part) is int and part >= 0 for part in value)
    )


def _valid_deck_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= _SAFE_COMPONENT_LIMIT
        and not value.startswith((";", "#"))
        and not any(character in value for character in "\r\n=\0")
        and not any(ord(character) < 32 for character in value)
    )


def _valid_component(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= _SAFE_COMPONENT_LIMIT
        and value not in {".", ".."}
        and Path(value).name == value
        and not any(character in value for character in '<>:"/\\|?*\0')
        and not any(ord(character) < 32 for character in value)
        and not value.endswith((".", " "))
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(value)


__all__ = (
    "MAX_RUNTIME_TRANSACTION_FILES",
    "RUNTIME_TRANSACTION_SCHEMA_VERSION",
    "RuntimeTransactionJournal",
    "RuntimeTransactionPhase",
    "RuntimeCleanupEntry",
    "load_runtime_transaction_journals",
    "read_runtime_transaction_journal",
    "runtime_transaction_journal_bytes",
    "runtime_transaction_journal_path",
    "write_runtime_transaction_journal",
)
