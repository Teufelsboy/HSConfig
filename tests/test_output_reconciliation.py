from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from hsconfig import output_reconciliation


IDENTITY = (1, 2, 3)
OTHER_IDENTITY = (4, 5, 6)


def _transaction(**changes: object) -> output_reconciliation._RootTransaction:
    base = output_reconciliation._RootTransaction(
        transaction_id="fixture",
        outputs_name="outputs",
        parent_identity=IDENTITY,
        transaction_identity=(10, 11, 12),
        journal_identity=(13, 14, 15),
        live_identity=IDENTITY,
        staged_identity=OTHER_IDENTITY,
        previous_identity=None,
        approval_digest=None,
        legacy_manifest={"schema_version": 1},
        phase="building",
    )
    return replace(base, **changes)


def _empty_manifest() -> dict[str, object]:
    return {
        "schema_version": output_reconciliation._APPROVAL_SCHEMA,
        "outputs_name": "outputs",
        "parent_identity": list(IDENTITY),
        "outputs_identity": list(IDENTITY),
        "entries": [],
    }


def _valid_entry(relative_root: str = "Deck") -> dict[str, object]:
    nodes = (
        output_reconciliation._TreeNode(
            relative_path="config.json",
            identity=IDENTITY,
            node_type="file",
            size=2,
            content_sha256="sha256:" + ("a" * 64),
        ),
    )
    return {
        "relative_root": relative_root,
        "deck_name": "Fixture Deck",
        "root_identity": list(OTHER_IDENTITY),
        "tree_sha256": output_reconciliation._tree_content_sha256(nodes),
        "nodes": [
            {
                "relative_path": node.relative_path,
                "identity": list(node.identity),
                "node_type": node.node_type,
                "size": node.size,
                "content_sha256": node.content_sha256,
            }
            for node in nodes
        ],
    }


def test_manifest_parser_accepts_canonical_entries_and_default_outputs_name(
    tmp_path: Path,
) -> None:
    root = tmp_path / "outputs"
    manifest = _empty_manifest()
    manifest["entries"] = [_valid_entry()]

    entries = output_reconciliation._manifest_entries_at(manifest, root)

    assert len(entries) == 1
    assert entries[0].path == root / "Deck"
    assert entries[0].relative_root == "Deck"
    assert entries[0].nodes[0].relative_path == "config.json"


def test_manifest_parser_rejects_top_level_shape_and_identity_errors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "outputs"
    invalid_manifests = []
    for key, value in (
        ("schema_version", 999),
        ("outputs_name", "other"),
        ("entries", {}),
    ):
        manifest = _empty_manifest()
        manifest[key] = value
        invalid_manifests.append(manifest)
    missing_key = _empty_manifest()
    del missing_key["parent_identity"]
    invalid_manifests.append(missing_key)

    for manifest in invalid_manifests:
        with pytest.raises(ValueError, match="reconcile_legacy_manifest_invalid"):
            output_reconciliation._manifest_entries_at(manifest, root)


def test_manifest_parser_rejects_invalid_entry_and_node_boundaries(
    tmp_path: Path,
) -> None:
    root = tmp_path / "outputs"
    invalid_entries: list[object] = ["not-an-entry"]
    entry_without_key = _valid_entry()
    del entry_without_key["deck_name"]
    invalid_entries.append(entry_without_key)
    entry_mutations = [
        ("relative_root", "../Deck"),
        ("deck_name", 3),
        ("tree_sha256", "invalid"),
        ("nodes", {}),
    ]
    for key, value in entry_mutations:
        entry = _valid_entry()
        entry[key] = value
        invalid_entries.append(entry)

    node_mutations = [
        ("relative_path", "../escape"),
        ("node_type", "link"),
        ("size", True),
        ("size", -1),
        ("content_sha256", "invalid"),
    ]
    for key, value in node_mutations:
        entry = _valid_entry()
        entry["nodes"][0][key] = value  # type: ignore[index]
        invalid_entries.append(entry)
    missing_node_key = _valid_entry()
    del missing_node_key["nodes"][0]["identity"]  # type: ignore[index]
    invalid_entries.append(missing_node_key)
    directory_with_digest = _valid_entry()
    directory_with_digest["nodes"][0]["node_type"] = "directory"  # type: ignore[index]
    invalid_entries.append(directory_with_digest)
    stale_tree = _valid_entry()
    stale_tree["tree_sha256"] = "sha256:" + ("0" * 64)
    invalid_entries.append(stale_tree)

    for entry in invalid_entries:
        manifest = _empty_manifest()
        manifest["entries"] = [entry]
        with pytest.raises(ValueError, match="reconcile_legacy_manifest_invalid"):
            output_reconciliation._manifest_entries_at(manifest, root)


def test_manifest_parser_rejects_unsorted_and_casefold_duplicate_roots(
    tmp_path: Path,
) -> None:
    root = tmp_path / "outputs"
    for entries in (
        [_valid_entry("Zulu"), _valid_entry("Alpha")],
        [_valid_entry("Deck"), _valid_entry("deck")],
    ):
        manifest = _empty_manifest()
        manifest["entries"] = entries
        with pytest.raises(ValueError, match="reconcile_legacy_manifest_invalid"):
            output_reconciliation._manifest_entries_at(manifest, root)


def test_recovery_approval_truth_table_binds_optional_and_required_digests() -> None:
    transaction = _transaction()
    manifest_digest = "sha256:" + sha256(
        output_reconciliation._canonical_json_bytes(transaction.legacy_manifest)
    ).hexdigest()
    output_reconciliation._require_recovery_approval(transaction, None)
    output_reconciliation._require_recovery_approval(transaction, manifest_digest)
    with pytest.raises(ValueError, match="reconcile_legacy_approval_mismatch"):
        output_reconciliation._require_recovery_approval(
            transaction,
            "sha256:" + ("0" * 64),
        )

    required = replace(transaction, approval_digest="sha256:" + ("a" * 64))
    with pytest.raises(ValueError, match="reconcile_legacy_approval_required"):
        output_reconciliation._require_recovery_approval(required, None)
    with pytest.raises(ValueError, match="reconcile_legacy_approval_mismatch"):
        output_reconciliation._require_recovery_approval(
            required,
            "sha256:" + ("b" * 64),
        )
    output_reconciliation._require_recovery_approval(
        required,
        "sha256:" + ("a" * 64),
    )


def test_transition_validator_rejects_phase_previous_and_authority_changes() -> None:
    building = _transaction()
    staged = replace(building, phase="staged_ready")
    output_reconciliation._validate_transition(building, staged)

    with pytest.raises(ValueError, match="reconcile_transaction_phase_invalid"):
        output_reconciliation._validate_transition(
            building,
            replace(building, phase="terminal"),
        )
    with pytest.raises(ValueError, match="reconcile_transaction_previous_invalid"):
        output_reconciliation._validate_transition(
            staged,
            replace(staged, phase="previous_moved", previous_identity=OTHER_IDENTITY),
        )
    previous_moved = replace(
        staged,
        phase="previous_moved",
        previous_identity=staged.live_identity,
    )
    output_reconciliation._validate_transition(staged, previous_moved)
    with pytest.raises(ValueError, match="reconcile_transaction_previous_invalid"):
        output_reconciliation._validate_transition(
            previous_moved,
            replace(
                previous_moved,
                phase="live_committed",
                previous_identity=OTHER_IDENTITY,
            ),
        )
    with pytest.raises(ValueError, match="reconcile_transaction_authority_changed"):
        output_reconciliation._validate_transition(
            building,
            replace(staged, outputs_name="other"),
        )


def test_transaction_document_parser_rejects_wrong_shape_and_schema() -> None:
    with pytest.raises(ValueError, match="reconcile_transaction_invalid"):
        output_reconciliation._parse_root_transaction_document([])
    document = output_reconciliation._root_transaction_document(_transaction())
    missing = deepcopy(document)
    del missing["phase"]
    with pytest.raises(ValueError, match="reconcile_transaction_invalid"):
        output_reconciliation._parse_root_transaction_document(missing)
    wrong_schema = {**document, "schema_version": 999}
    with pytest.raises(ValueError, match="reconcile_transaction_invalid"):
        output_reconciliation._parse_root_transaction_document(wrong_schema)
    assert output_reconciliation._parse_root_transaction_document(document) == (
        _transaction()
    )


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"", "reconcile_transaction_invalid"),
        (b"{}", "reconcile_transaction_invalid"),
        (b"\n", "reconcile_transaction_invalid"),
        (b"not-json\n", "reconcile_transaction_invalid"),
        (b'{"generation":0}\n', "reconcile_transaction_invalid"),
    ],
)
def test_root_journal_parser_rejects_truncated_and_malformed_records(
    raw: bytes,
    reason: str,
) -> None:
    with pytest.raises(ValueError, match=reason):
        output_reconciliation._parse_root_journal(raw)


def _journal_record(
    transaction: output_reconciliation._RootTransaction,
    *,
    generation: int,
    previous_hash: str,
) -> tuple[bytes, str]:
    body = {
        "generation": generation,
        "previous_record_sha256": previous_hash,
        "schema_version": output_reconciliation._ROOT_TRANSACTION_SCHEMA,
        "transaction": output_reconciliation._root_transaction_document(transaction),
    }
    record_hash = "sha256:" + sha256(
        output_reconciliation._canonical_json_bytes(body)
    ).hexdigest()
    record = {**body, "record_sha256": record_hash}
    return output_reconciliation._canonical_json_bytes(record) + b"\n", record_hash


def test_root_journal_parser_accepts_canonical_chain_and_marks_partial_tail() -> None:
    building = _transaction()
    first, first_hash = _journal_record(
        building,
        generation=0,
        previous_hash=output_reconciliation._ZERO_RECORD_HASH,
    )
    staged = replace(building, phase="staged_ready")
    second, second_hash = _journal_record(
        staged,
        generation=1,
        previous_hash=first_hash,
    )

    state = output_reconciliation._parse_root_journal(first + second + b"partial")

    assert state.transaction == staged
    assert state.generation == 1
    assert state.record_hash == second_hash
    assert state.valid_length == len(first + second)
    assert state.has_partial_tail is True


def test_root_journal_parser_rejects_noncanonical_and_broken_hash_chain() -> None:
    transaction = _transaction()
    canonical, _record_hash = _journal_record(
        transaction,
        generation=0,
        previous_hash=output_reconciliation._ZERO_RECORD_HASH,
    )
    record = json.loads(canonical)

    noncanonical = json.dumps(record, sort_keys=True).encode("utf-8") + b"\n"
    with pytest.raises(ValueError, match="reconcile_transaction_noncanonical"):
        output_reconciliation._parse_root_journal(noncanonical)

    for key, value in (
        ("generation", 1),
        ("previous_record_sha256", "sha256:" + ("1" * 64)),
        ("record_sha256", "sha256:" + ("2" * 64)),
    ):
        corrupted = {**record, key: value}
        raw = output_reconciliation._canonical_json_bytes(corrupted) + b"\n"
        with pytest.raises(
            ValueError,
            match="reconcile_transaction_hash_chain_invalid",
        ):
            output_reconciliation._parse_root_journal(raw)


@pytest.mark.parametrize(
    "value",
    [None, (), [1, 2], [1, 2, 3, 4], [True, 2, 3], [-1, 2, 3]],
)
def test_identity_parser_rejects_ambiguous_filesystem_identities(value: object) -> None:
    with pytest.raises(ValueError, match="reconcile_identity_invalid"):
        output_reconciliation._parse_identity(value)


def test_optional_identity_parser_preserves_none_and_canonical_identity() -> None:
    assert output_reconciliation._parse_identity_or_none(None) is None
    assert output_reconciliation._parse_identity_or_none([1, 2, 3]) == IDENTITY


def test_coordinator_locator_ignores_empty_residue_and_rejects_foreign_state(
    tmp_path: Path,
) -> None:
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    empty_cleanup = tmp_path / (
        output_reconciliation._ROOT_CLEANUP_PREFIX + ("a" * 32)
    )
    empty_cleanup.mkdir()
    assert output_reconciliation._locate_root_coordinator(tmp_path) is None

    active = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    active.mkdir()
    assert output_reconciliation._locate_root_coordinator(tmp_path) == active

    foreign = tmp_path / ".hsconfig-output-reconcile-foreign"
    foreign.mkdir()
    with pytest.raises(ValueError, match="reconcile_coordinator_foreign"):
        output_reconciliation._locate_root_coordinator(tmp_path)


def test_coordinator_locator_validates_cleanup_and_prepare_residue(
    tmp_path: Path,
) -> None:
    cleanup = tmp_path / (output_reconciliation._ROOT_CLEANUP_PREFIX + ("a" * 32))
    cleanup.mkdir()
    (cleanup / "foreign").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="reconcile_cleanup_residue"):
        output_reconciliation._locate_root_coordinator(tmp_path)

    (cleanup / "foreign").unlink()
    cleanup.rmdir()
    prepare = tmp_path / (output_reconciliation._ROOT_PREPARE_PREFIX + ("b" * 32))
    prepare.mkdir()
    (prepare / output_reconciliation._ROOT_JOURNAL_NAME).write_bytes(b"journal")
    (prepare / "foreign").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="reconcile_prepare_residue"):
        output_reconciliation._locate_root_coordinator(tmp_path)


def test_plain_tree_capture_binds_nested_content_and_parent_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Deck"
    nested = root / "nested"
    nested.mkdir(parents=True)
    payload = nested / "payload.json"
    payload.write_text('{"ok":true}', encoding="utf-8")

    nodes = output_reconciliation._capture_plain_tree(root)
    entry = output_reconciliation._DeletionEntry(
        path=root,
        relative_root="Deck",
        identity=output_reconciliation.path_identity(root),
        deck_name="Fixture Deck",
        nodes=nodes,
        tree_sha256=output_reconciliation._tree_content_sha256(nodes),
    )

    assert [node.relative_path for node in nodes] == [
        "nested",
        "nested/payload.json",
    ]
    assert output_reconciliation._manifest_parent_identity(
        entry,
        nodes[0],
    ) == entry.identity
    assert output_reconciliation._manifest_parent_identity(
        entry,
        nodes[1],
    ) == nodes[0].identity
    output_reconciliation._require_deletion_manifest_unchanged(root.parent, (entry,))

    payload.write_text('{"ok":false}', encoding="utf-8")
    with pytest.raises(ValueError, match="reconcile_deletion_identity_changed"):
        output_reconciliation._require_deletion_manifest_unchanged(
            root.parent,
            (entry,),
        )


def test_plain_json_reader_rejects_unsafe_and_malformed_files(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text('{"ok":true}', encoding="utf-8")
    assert output_reconciliation._read_plain_json(valid) == {"ok": True}

    malformed = tmp_path / "malformed.json"
    malformed.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="reconcile_json_invalid"):
        output_reconciliation._read_plain_json(malformed)
    with pytest.raises(ValueError, match="reconcile_json_file_unsafe"):
        output_reconciliation._read_plain_json(tmp_path)


def test_transaction_authority_validation_accepts_bound_empty_initial_state(
    tmp_path: Path,
) -> None:
    transaction_root = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    transaction_root.mkdir()
    parent_identity = output_reconciliation.path_identity(tmp_path)
    transaction = output_reconciliation._RootTransaction(
        transaction_id="a" * 32,
        outputs_name="outputs",
        parent_identity=parent_identity,
        transaction_identity=output_reconciliation.path_identity(transaction_root),
        journal_identity=IDENTITY,
        live_identity=None,
        staged_identity=OTHER_IDENTITY,
        previous_identity=None,
        approval_digest=None,
        legacy_manifest={
            "schema_version": output_reconciliation._APPROVAL_SCHEMA,
            "outputs_name": "outputs",
            "parent_identity": list(parent_identity),
            "outputs_identity": None,
            "entries": [],
        },
        phase="building",
    )

    output_reconciliation._validate_root_transaction_document(
        transaction,
        transaction_root=transaction_root,
        expected_outputs_name="outputs",
    )


def test_transaction_authority_validation_rejects_unbound_recovery_state(
    tmp_path: Path,
) -> None:
    transaction_root = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    transaction_root.mkdir()
    parent_identity = output_reconciliation.path_identity(tmp_path)
    valid_manifest = {
        "schema_version": output_reconciliation._APPROVAL_SCHEMA,
        "outputs_name": "outputs",
        "parent_identity": list(parent_identity),
        "outputs_identity": None,
        "entries": [],
    }
    transaction = output_reconciliation._RootTransaction(
        transaction_id="a" * 32,
        outputs_name="outputs",
        parent_identity=parent_identity,
        transaction_identity=output_reconciliation.path_identity(transaction_root),
        journal_identity=IDENTITY,
        live_identity=None,
        staged_identity=OTHER_IDENTITY,
        previous_identity=None,
        approval_digest=None,
        legacy_manifest=valid_manifest,
        phase="building",
    )
    malformed_manifest = {**valid_manifest, "entries": {}}
    nonempty_unapproved = {**valid_manifest, "entries": [{}]}
    invalid_cases = (
        replace(transaction, transaction_id="not-a-transaction-id"),
        replace(transaction, outputs_name="other"),
        replace(transaction, phase="future"),
        replace(transaction, transaction_identity=IDENTITY),
        replace(transaction, legacy_manifest=[]),
        replace(transaction, approval_digest="not-a-digest"),
        replace(transaction, legacy_manifest=malformed_manifest),
        replace(transaction, legacy_manifest=nonempty_unapproved),
        replace(
            transaction,
            legacy_manifest={
                **valid_manifest,
                "parent_identity": list(OTHER_IDENTITY),
            },
        ),
        replace(
            transaction,
            legacy_manifest={
                **valid_manifest,
                "outputs_identity": list(OTHER_IDENTITY),
            },
        ),
        replace(transaction, previous_identity=OTHER_IDENTITY),
    )

    for invalid in invalid_cases:
        with pytest.raises(ValueError, match="reconcile_transaction_invalid"):
            output_reconciliation._validate_root_transaction_document(
                invalid,
                transaction_root=transaction_root,
                expected_outputs_name="outputs",
            )


def _authority(*names: str) -> output_reconciliation._CatalogAuthority:
    return output_reconciliation._CatalogAuthority(
        catalog_path=Path("catalog.json"),
        names=names,
        fingerprints={name: f"fingerprint-{name}" for name in names},
    )


def _empty_manifest_for(
    parent: Path,
    *,
    outputs_identity: tuple[int, int, int] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": output_reconciliation._APPROVAL_SCHEMA,
        "outputs_name": "outputs",
        "parent_identity": list(output_reconciliation.path_identity(parent)),
        "outputs_identity": (
            list(outputs_identity) if outputs_identity is not None else None
        ),
        "entries": [],
    }


def test_legacy_proposal_rejects_non_object_manifest() -> None:
    proposal = output_reconciliation.LegacyDeletionProposal(
        manifest_bytes=b"[]",
        approval_digest="sha256:" + ("0" * 64),
    )

    with pytest.raises(ValueError, match="reconcile_legacy_manifest_invalid"):
        proposal.manifest


def test_coordinator_locator_rejects_multiple_cleanup_prepare_and_kinds(
    tmp_path: Path,
) -> None:
    for prefix, reason in (
        (output_reconciliation._ROOT_CLEANUP_PREFIX, "reconcile_cleanup_multiple"),
        (output_reconciliation._ROOT_PREPARE_PREFIX, "reconcile_prepare_multiple"),
    ):
        parent = tmp_path / prefix.removesuffix("-")
        parent.mkdir()
        for suffix in ("a" * 32, "b" * 32):
            coordinator = parent / f"{prefix}{suffix}"
            coordinator.mkdir()
            (coordinator / output_reconciliation._ROOT_JOURNAL_NAME).touch()
        with pytest.raises(ValueError, match=reason):
            output_reconciliation._locate_root_coordinator(parent)

    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / output_reconciliation._ROOT_TRANSACTION_NAME).mkdir()
    cleanup = mixed / (output_reconciliation._ROOT_CLEANUP_PREFIX + ("c" * 32))
    cleanup.mkdir()
    (cleanup / output_reconciliation._ROOT_JOURNAL_NAME).touch()
    with pytest.raises(ValueError, match="reconcile_coordinator_multiple"):
        output_reconciliation._locate_root_coordinator(mixed)


def test_create_empty_journal_binds_parent_and_creates_plain_empty_file(
    tmp_path: Path,
) -> None:
    journal = tmp_path / output_reconciliation._ROOT_JOURNAL_NAME
    parent_identity = output_reconciliation.path_identity(tmp_path)

    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        output_reconciliation._create_empty_journal(
            journal,
            expected_parent_identity=OTHER_IDENTITY,
        )

    identity = output_reconciliation._create_empty_journal(
        journal,
        expected_parent_identity=parent_identity,
    )

    assert journal.read_bytes() == b""
    assert output_reconciliation.path_identity(journal) == identity


def test_root_journal_rejects_oversized_tail_and_nonbuilding_first_record() -> None:
    building, _building_hash = _journal_record(
        _transaction(),
        generation=0,
        previous_hash=output_reconciliation._ZERO_RECORD_HASH,
    )
    oversized_tail = b"x" * (output_reconciliation._ROOT_JOURNAL_RECORD_LIMIT + 1)
    with pytest.raises(ValueError, match="reconcile_transaction_journal_overflow"):
        output_reconciliation._parse_root_journal(building + oversized_tail)

    nonbuilding, _nonbuilding_hash = _journal_record(
        _transaction(phase="staged_ready"),
        generation=0,
        previous_hash=output_reconciliation._ZERO_RECORD_HASH,
    )
    with pytest.raises(ValueError, match="reconcile_transaction_phase_invalid"):
        output_reconciliation._parse_root_journal(nonbuilding)


def test_append_root_transition_truncates_partial_tail_before_next_record(
    tmp_path: Path,
) -> None:
    journal = tmp_path / output_reconciliation._ROOT_JOURNAL_NAME
    journal_identity = output_reconciliation._create_empty_journal(
        journal,
        expected_parent_identity=output_reconciliation.path_identity(tmp_path),
    )
    building = _transaction(journal_identity=journal_identity)
    state = output_reconciliation._append_root_transition(
        journal,
        None,
        building,
        fault_hook=lambda _stage: None,
    )
    with journal.open("ab") as stream:
        stream.write(b"partial-record")

    staged = replace(building, phase="staged_ready")
    next_state = output_reconciliation._append_root_transition(
        journal,
        state,
        staged,
        fault_hook=lambda _stage: None,
    )

    reparsed = output_reconciliation._parse_root_journal(journal.read_bytes())
    assert next_state == reparsed
    assert reparsed.transaction.phase == "staged_ready"
    assert reparsed.has_partial_tail is False


def test_append_root_transition_rejects_changed_empty_journal_and_phase(
    tmp_path: Path,
) -> None:
    changed = tmp_path / "changed.ndjson"
    changed.write_bytes(b"residue")
    changed_transaction = _transaction(
        journal_identity=output_reconciliation.path_identity(changed)
    )
    with pytest.raises(ValueError, match="reconcile_transaction_changed"):
        output_reconciliation._append_root_transition(
            changed,
            None,
            changed_transaction,
            fault_hook=lambda _stage: None,
        )

    nonbuilding = tmp_path / "nonbuilding.ndjson"
    nonbuilding.touch()
    nonbuilding_transaction = _transaction(
        journal_identity=output_reconciliation.path_identity(nonbuilding),
        phase="staged_ready",
    )
    with pytest.raises(ValueError, match="reconcile_transaction_phase_invalid"):
        output_reconciliation._append_root_transition(
            nonbuilding,
            None,
            nonbuilding_transaction,
            fault_hook=lambda _stage: None,
        )


def test_append_root_transition_rejects_stale_state_and_oversized_record(
    tmp_path: Path,
) -> None:
    journal = tmp_path / output_reconciliation._ROOT_JOURNAL_NAME
    journal.touch()
    journal_identity = output_reconciliation.path_identity(journal)
    transaction = _transaction(journal_identity=journal_identity)
    state = output_reconciliation._append_root_transition(
        journal,
        None,
        transaction,
        fault_hook=lambda _stage: None,
    )
    stale = replace(state, valid_length=state.valid_length + 1)
    with pytest.raises(ValueError, match="reconcile_transaction_changed"):
        output_reconciliation._append_root_transition(
            journal,
            stale,
            replace(transaction, phase="staged_ready"),
            fault_hook=lambda _stage: None,
        )

    oversized = tmp_path / "oversized.ndjson"
    oversized.touch()
    oversized_transaction = _transaction(
        journal_identity=output_reconciliation.path_identity(oversized),
        legacy_manifest={
            "payload": "x" * output_reconciliation._ROOT_JOURNAL_RECORD_LIMIT
        },
    )
    with pytest.raises(ValueError, match="reconcile_transaction_record_overflow"):
        output_reconciliation._append_root_transition(
            oversized,
            None,
            oversized_transaction,
            fault_hook=lambda _stage: None,
        )


def test_journal_descriptor_rejects_oversized_file(tmp_path: Path) -> None:
    journal = tmp_path / output_reconciliation._ROOT_JOURNAL_NAME
    maximum = output_reconciliation._ROOT_JOURNAL_RECORD_LIMIT * (
        output_reconciliation._ROOT_JOURNAL_GENERATION_LIMIT + 1
    )
    with journal.open("wb") as stream:
        stream.truncate(maximum + 1)
    descriptor = os.open(journal, os.O_RDONLY)
    try:
        with pytest.raises(
            ValueError,
            match="reconcile_transaction_journal_overflow",
        ):
            output_reconciliation._read_journal_descriptor(descriptor)
    finally:
        os.close(descriptor)


def test_load_root_transaction_accepts_bound_journal_and_rejects_wrong_name(
    tmp_path: Path,
) -> None:
    transaction_root = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    transaction_root.mkdir()
    journal = transaction_root / output_reconciliation._ROOT_JOURNAL_NAME
    journal.touch()
    transaction = output_reconciliation._RootTransaction(
        transaction_id="a" * 32,
        outputs_name="outputs",
        parent_identity=output_reconciliation.path_identity(tmp_path),
        transaction_identity=output_reconciliation.path_identity(transaction_root),
        journal_identity=output_reconciliation.path_identity(journal),
        live_identity=None,
        staged_identity=OTHER_IDENTITY,
        previous_identity=None,
        approval_digest=None,
        legacy_manifest=_empty_manifest_for(tmp_path),
        phase="building",
    )
    state = output_reconciliation._append_root_transition(
        journal,
        None,
        transaction,
        fault_hook=lambda _stage: None,
    )

    loaded, loaded_path = output_reconciliation._load_root_transaction(
        transaction_root,
        expected_outputs_name="outputs",
    )
    assert loaded == state
    assert loaded_path == journal

    foreign = tmp_path / "foreign"
    transaction_root.rename(foreign)
    with pytest.raises(ValueError, match="reconcile_transaction_name_invalid"):
        output_reconciliation._load_root_transaction(
            foreign,
            expected_outputs_name="outputs",
        )


def test_load_root_transaction_rejects_bound_journal_identity_change(
    tmp_path: Path,
) -> None:
    transaction_root = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    transaction_root.mkdir()
    journal = transaction_root / output_reconciliation._ROOT_JOURNAL_NAME
    journal.touch()
    transaction = output_reconciliation._RootTransaction(
        transaction_id="b" * 32,
        outputs_name="outputs",
        parent_identity=output_reconciliation.path_identity(tmp_path),
        transaction_identity=output_reconciliation.path_identity(transaction_root),
        journal_identity=OTHER_IDENTITY,
        live_identity=None,
        staged_identity=IDENTITY,
        previous_identity=None,
        approval_digest=None,
        legacy_manifest=_empty_manifest_for(tmp_path),
        phase="building",
    )
    record, _record_hash = _journal_record(
        transaction,
        generation=0,
        previous_hash=output_reconciliation._ZERO_RECORD_HASH,
    )
    journal.write_bytes(record)

    with pytest.raises(
        ValueError,
        match="reconcile_transaction_journal_identity_changed",
    ):
        output_reconciliation._load_root_transaction(
            transaction_root,
            expected_outputs_name="outputs",
        )


def test_reconstruct_root_phase_validates_abort_and_terminal_states(
    tmp_path: Path,
) -> None:
    abort_parent = tmp_path / "abort"
    transaction_root = abort_parent / output_reconciliation._ROOT_TRANSACTION_NAME
    transaction_root.mkdir(parents=True)
    root = abort_parent / "outputs"
    root.mkdir()
    old_identity = output_reconciliation.path_identity(root)
    aborted = _transaction(
        parent_identity=output_reconciliation.path_identity(abort_parent),
        transaction_identity=output_reconciliation.path_identity(transaction_root),
        live_identity=old_identity,
        phase="aborted",
    )
    assert (
        output_reconciliation._reconstruct_root_phase(
            root,
            transaction_root,
            aborted,
            _authority(),
        )
        == "aborted"
    )
    staged = transaction_root / "staged"
    staged.mkdir()
    aborting = replace(
        aborted,
        staged_identity=output_reconciliation.path_identity(staged),
        phase="aborting",
    )
    assert (
        output_reconciliation._reconstruct_root_phase(
            root,
            transaction_root,
            aborting,
            _authority(),
        )
        == "aborting"
    )
    with pytest.raises(
        ValueError,
        match="reconcile_transaction_physical_state_invalid",
    ):
        output_reconciliation._reconstruct_root_phase(
            root,
            transaction_root,
            aborted,
            _authority(),
        )

    terminal_parent = tmp_path / "terminal"
    terminal_transaction_root = (
        terminal_parent / output_reconciliation._ROOT_TRANSACTION_NAME
    )
    terminal_transaction_root.mkdir(parents=True)
    staged = terminal_transaction_root / "staged"
    staged.mkdir()
    new_identity = output_reconciliation.path_identity(staged)
    terminal_root = terminal_parent / "outputs"
    staged.rename(terminal_root)
    terminal = _transaction(
        parent_identity=output_reconciliation.path_identity(terminal_parent),
        transaction_identity=output_reconciliation.path_identity(
            terminal_transaction_root
        ),
        live_identity=None,
        staged_identity=new_identity,
        phase="terminal",
    )
    assert (
        output_reconciliation._reconstruct_root_phase(
            terminal_root,
            terminal_transaction_root,
            terminal,
            _authority(),
        )
        == "terminal"
    )
    (terminal_transaction_root / "previous").mkdir()
    with pytest.raises(
        ValueError,
        match="reconcile_transaction_physical_state_invalid",
    ):
        output_reconciliation._reconstruct_root_phase(
            terminal_root,
            terminal_transaction_root,
            terminal,
            _authority(),
        )


def test_reconstruct_root_phase_recovers_each_completed_swap_boundary(
    tmp_path: Path,
) -> None:
    transaction_root = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    transaction_root.mkdir()
    root = tmp_path / "outputs"
    root.mkdir()
    old_identity = output_reconciliation.path_identity(root)
    staged = transaction_root / "staged"
    staged.mkdir()
    new_identity = output_reconciliation.path_identity(staged)
    transaction = _transaction(
        parent_identity=output_reconciliation.path_identity(tmp_path),
        transaction_identity=output_reconciliation.path_identity(transaction_root),
        live_identity=old_identity,
        staged_identity=new_identity,
        phase="staged_ready",
    )

    assert (
        output_reconciliation._reconstruct_root_phase(
            root,
            transaction_root,
            transaction,
            _authority(),
        )
        == "staged_ready"
    )
    previous = transaction_root / "previous"
    root.rename(previous)
    assert (
        output_reconciliation._reconstruct_root_phase(
            root,
            transaction_root,
            transaction,
            _authority(),
        )
        == "previous_moved"
    )
    staged.rename(root)
    assert (
        output_reconciliation._reconstruct_root_phase(
            root,
            transaction_root,
            transaction,
            _authority(),
        )
        == "live_committed"
    )
    previous.rmdir()
    assert (
        output_reconciliation._reconstruct_root_phase(
            root,
            transaction_root,
            transaction,
            _authority(),
        )
        == "terminal"
    )


def test_append_inferred_transitions_rejects_skips_mismatch_and_regression(
    tmp_path: Path,
) -> None:
    building = output_reconciliation._JournalState(
        transaction=_transaction(),
        generation=0,
        record_hash=output_reconciliation._ZERO_RECORD_HASH,
        valid_length=0,
        has_partial_tail=False,
    )
    with pytest.raises(ValueError, match="reconcile_transaction_phase_invalid"):
        output_reconciliation._append_inferred_transitions(
            tmp_path / "journal",
            building,
            "live_committed",
            fault_hook=lambda _stage: None,
        )

    terminal = replace(
        building,
        transaction=replace(building.transaction, phase="terminal"),
    )
    with pytest.raises(ValueError, match="reconcile_transaction_phase_invalid"):
        output_reconciliation._append_inferred_transitions(
            tmp_path / "journal",
            terminal,
            "aborted",
            fault_hook=lambda _stage: None,
        )

    committed = replace(
        building,
        transaction=replace(building.transaction, phase="live_committed"),
    )
    with pytest.raises(ValueError, match="reconcile_transaction_phase_invalid"):
        output_reconciliation._append_inferred_transitions(
            tmp_path / "journal",
            committed,
            "previous_moved",
            fault_hook=lambda _stage: None,
        )


def test_cleanup_tombstone_publication_rejects_nonterminal_and_wrong_name(
    tmp_path: Path,
) -> None:
    active = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    active.mkdir()
    transaction = _transaction(
        transaction_id="a" * 32,
        parent_identity=output_reconciliation.path_identity(tmp_path),
        transaction_identity=output_reconciliation.path_identity(active),
    )
    with pytest.raises(ValueError, match="reconcile_transaction_not_terminal"):
        output_reconciliation._publish_cleanup_tombstone(
            active,
            transaction,
            fault_hook=lambda _stage: None,
        )

    wrong = tmp_path / "wrong"
    wrong.mkdir()
    terminal = replace(
        transaction,
        transaction_identity=output_reconciliation.path_identity(wrong),
        phase="terminal",
    )
    with pytest.raises(ValueError, match="reconcile_cleanup_name_invalid"):
        output_reconciliation._publish_cleanup_tombstone(
            wrong,
            terminal,
            fault_hook=lambda _stage: None,
        )


def test_journal_only_cleanup_lock_creation_is_identity_and_phase_bound(
    tmp_path: Path,
) -> None:
    transaction_id = "a" * 32
    coordinator = tmp_path / (
        output_reconciliation._ROOT_CLEANUP_PREFIX + transaction_id
    )
    coordinator.mkdir()
    journal = coordinator / output_reconciliation._ROOT_JOURNAL_NAME
    journal.touch()
    transaction = _transaction(
        transaction_id=transaction_id,
        parent_identity=output_reconciliation.path_identity(tmp_path),
        transaction_identity=output_reconciliation.path_identity(coordinator),
        journal_identity=output_reconciliation.path_identity(journal),
        phase="terminal",
    )
    state = output_reconciliation._JournalState(
        transaction=transaction,
        generation=1,
        record_hash=output_reconciliation._ZERO_RECORD_HASH,
        valid_length=0,
        has_partial_tail=False,
    )

    assert output_reconciliation._journal_only_cleanup_lock_may_create(
        coordinator,
        state,
        journal,
    )
    (coordinator / "lease.lock").touch()
    assert not output_reconciliation._journal_only_cleanup_lock_may_create(
        coordinator,
        state,
        journal,
    )
    with pytest.raises(ValueError, match="reconcile_transaction_cleanup_invalid"):
        output_reconciliation._journal_only_cleanup_lock_may_create(
            coordinator,
            replace(state, transaction=replace(transaction, phase="building")),
            journal,
        )
    assert not output_reconciliation._journal_only_cleanup_lock_may_create(
        tmp_path / "foreign",
        state,
        journal,
    )


def test_transaction_authority_rejects_manifest_deck_outside_catalog() -> None:
    manifest = _empty_manifest()
    manifest["entries"] = [_valid_entry()]
    transaction = _transaction(legacy_manifest=manifest)

    with pytest.raises(
        ValueError,
        match="reconcile_transaction_legacy_authority_invalid",
    ):
        output_reconciliation._validate_root_transaction_authority(
            transaction,
            _authority("Different Deck"),
        )


def test_approval_manifest_current_handles_absent_new_root_and_previous_fallback(
    tmp_path: Path,
) -> None:
    root = tmp_path / "outputs"
    absent = _transaction(
        outputs_name="outputs",
        parent_identity=output_reconciliation.path_identity(tmp_path),
        live_identity=None,
        legacy_manifest=_empty_manifest_for(tmp_path),
    )
    output_reconciliation._require_approval_manifest_current(root, absent)
    root.mkdir()
    with pytest.raises(ValueError, match="reconcile_output_root_changed"):
        output_reconciliation._require_approval_manifest_current(root, absent)
    root.rmdir()

    transaction_root = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    transaction_root.mkdir()
    previous = transaction_root / "previous"
    previous.mkdir()
    previous_identity = output_reconciliation.path_identity(previous)
    fallback = replace(
        absent,
        live_identity=previous_identity,
        legacy_manifest=_empty_manifest_for(
            tmp_path,
            outputs_identity=previous_identity,
        ),
    )
    output_reconciliation._require_approval_manifest_current(root, fallback)


def test_remove_approved_previous_rejects_unexpected_state_and_removes_empty(
    tmp_path: Path,
) -> None:
    transaction_root = tmp_path / output_reconciliation._ROOT_TRANSACTION_NAME
    transaction_root.mkdir()
    previous = transaction_root / "previous"
    previous.mkdir()
    base = _transaction(
        outputs_name="outputs",
        parent_identity=output_reconciliation.path_identity(tmp_path),
        transaction_identity=output_reconciliation.path_identity(transaction_root),
        live_identity=None,
        previous_identity=None,
        legacy_manifest=_empty_manifest_for(tmp_path),
        phase="live_committed",
    )
    with pytest.raises(ValueError, match="reconcile_transaction_previous_invalid"):
        output_reconciliation._remove_approved_previous(
            previous,
            base,
            fault_hook=lambda _stage: None,
        )

    previous_identity = output_reconciliation.path_identity(previous)
    approved = replace(base, previous_identity=previous_identity)
    (previous / "foreign").touch()
    with pytest.raises(ValueError, match="reconcile_deletion_identity_changed"):
        output_reconciliation._remove_approved_previous(
            previous,
            approved,
            fault_hook=lambda _stage: None,
        )
    (previous / "foreign").unlink()
    output_reconciliation._remove_approved_previous(
        previous,
        approved,
        fault_hook=lambda _stage: None,
    )
    assert not previous.exists()
    output_reconciliation._remove_approved_previous(
        previous,
        approved,
        fault_hook=lambda _stage: None,
    )


def test_remove_process_owned_tree_removes_nested_content_and_reports_progress(
    tmp_path: Path,
) -> None:
    staged = tmp_path / "staged"
    nested = staged / "nested"
    nested.mkdir(parents=True)
    (nested / "payload.json").write_text("{}", encoding="utf-8")
    stages: list[str] = []

    output_reconciliation._remove_process_owned_tree(
        staged,
        expected_identity=output_reconciliation.path_identity(staged),
        expected_parent_identity=output_reconciliation.path_identity(tmp_path),
        fault_hook=stages.append,
    )

    assert not staged.exists()
    assert stages == [
        "during_abort_staging_cleanup",
        "during_abort_staging_cleanup",
    ]
    output_reconciliation._remove_process_owned_tree(
        staged,
        expected_identity=IDENTITY,
        expected_parent_identity=OTHER_IDENTITY,
    )


def test_legacy_deck_identity_and_capture_manifest_bind_catalog_name(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    deck = outputs / "Deck"
    reports = deck / "reports"
    reports.mkdir(parents=True)
    (reports / "input_manifest.json").write_text(
        '{"deck_name":"Deck"}',
        encoding="utf-8",
    )
    authority = _authority("Deck")

    assert output_reconciliation._legacy_deck_identity(deck, authority) == "Deck"
    entries = output_reconciliation._capture_deletion_manifest(outputs, authority)
    assert [(entry.relative_root, entry.deck_name) for entry in entries] == [
        ("Deck", "Deck")
    ]
    assert entries[0].nodes[-1].relative_path == "reports/input_manifest.json"

    (reports / "input_manifest.json").write_text(
        '{"deck_name":"Other"}',
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="reconcile_unexpected_stable_output_entry",
    ):
        output_reconciliation._capture_deletion_manifest(
            outputs,
            _authority("Deck", "Other"),
        )


def test_plain_tree_rejects_hardlinked_files(tmp_path: Path) -> None:
    root = tmp_path / "Deck"
    root.mkdir()
    source = root / "source.json"
    alias = root / "alias.json"
    source.write_text("{}", encoding="utf-8")
    os.link(source, alias)

    with pytest.raises(ValueError, match="reconcile_deletion_hardlink"):
        output_reconciliation._capture_plain_tree(root)


def test_empty_deletion_manifest_detects_new_entries_and_removal_is_idempotent(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    output_reconciliation._require_deletion_manifest_unchanged(outputs, ())
    outputs.mkdir()
    output_reconciliation._require_deletion_manifest_unchanged(outputs, ())
    (outputs / "foreign").touch()
    with pytest.raises(ValueError, match="reconcile_output_root_changed"):
        output_reconciliation._require_deletion_manifest_unchanged(outputs, ())
    (outputs / "foreign").unlink()
    output_reconciliation._remove_deletion_manifest(outputs, ())


def test_remove_manifest_entry_tolerates_already_removed_child(tmp_path: Path) -> None:
    root = tmp_path / "Deck"
    root.mkdir()
    payload = root / "payload.json"
    payload.write_text("{}", encoding="utf-8")
    nodes = output_reconciliation._capture_plain_tree(root)
    entry = output_reconciliation._DeletionEntry(
        path=root,
        relative_root="Deck",
        identity=output_reconciliation.path_identity(root),
        deck_name="Deck",
        nodes=nodes,
        tree_sha256=output_reconciliation._tree_content_sha256(nodes),
    )
    payload.unlink()

    output_reconciliation._remove_manifest_entry(entry)

    assert not root.exists()


def test_manifest_parent_requires_exactly_one_directory_parent() -> None:
    entry = output_reconciliation._DeletionEntry(
        path=Path("Deck"),
        relative_root="Deck",
        identity=IDENTITY,
        deck_name="Deck",
        nodes=(
            output_reconciliation._TreeNode(
                relative_path="nested/payload.json",
                identity=OTHER_IDENTITY,
                node_type="file",
                size=2,
                content_sha256="sha256:" + ("a" * 64),
            ),
        ),
        tree_sha256="sha256:" + ("b" * 64),
    )

    with pytest.raises(ValueError, match="reconcile_legacy_manifest_invalid"):
        output_reconciliation._manifest_parent_identity(entry, entry.nodes[0])


def test_plain_directory_validation_distinguishes_missing_and_unsafe(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="reconcile_directory_missing"):
        output_reconciliation._require_plain_directory(missing)

    plain_file = tmp_path / "file"
    plain_file.touch()
    with pytest.raises(ValueError, match="reconcile_directory_unsafe"):
        output_reconciliation._require_plain_directory(plain_file)


def _proposal(entries: object) -> output_reconciliation.LegacyDeletionProposal:
    manifest_bytes = json.dumps({"entries": entries}).encode("utf-8")
    return output_reconciliation.LegacyDeletionProposal(
        manifest_bytes=manifest_bytes,
        approval_digest="sha256:" + sha256(manifest_bytes).hexdigest(),
    )


def test_apply_under_election_requires_canonical_manifest_and_exact_approval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "outputs"
    authority = _authority("Deck")
    monkeypatch.setattr(output_reconciliation, "_recover_root_transaction", lambda *args, **kwargs: None)
    monkeypatch.setattr(output_reconciliation, "_scan_inventory", lambda *args, **kwargs: object())
    monkeypatch.setattr(output_reconciliation, "_inventory_is_current", lambda value: False)

    for proposal, approval, reason in (
        (_proposal({}), None, "reconcile_legacy_manifest_invalid"),
        (_proposal([{"legacy": True}]), None, "reconcile_legacy_approval_required"),
        (_proposal([{"legacy": True}]), "sha256:wrong", "reconcile_legacy_approval_mismatch"),
        (_proposal([]), "sha256:wrong", "reconcile_legacy_approval_mismatch"),
    ):
        monkeypatch.setattr(
            output_reconciliation,
            "propose_legacy_deletion",
            lambda **kwargs: proposal,
        )
        with pytest.raises(ValueError, match=reason):
            output_reconciliation._apply_audited_outputs_under_election(
                root,
                authority,
                catalog_path=Path("catalog.json"),
                legacy_approval_digest=approval,
                fault_hook=output_reconciliation.no_fault,
            )


def test_start_transaction_refuses_a_preexisting_coordinator(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "outputs"
    root.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        output_reconciliation,
        "_locate_root_coordinator",
        lambda parent: parent / "existing",
    )

    with pytest.raises(ValueError, match="reconcile_transaction_preexisting"):
        output_reconciliation._start_root_transaction(
            root,
            _authority("Deck"),
            proposal=_proposal([]),
            fault_hook=output_reconciliation.no_fault,
        )


def test_cleanup_lock_creation_is_limited_to_terminal_journal_only_state(
    tmp_path: Path,
) -> None:
    coordinator = tmp_path / f"{output_reconciliation._ROOT_CLEANUP_PREFIX}fixture"
    coordinator.mkdir()
    journal = coordinator / output_reconciliation._ROOT_JOURNAL_NAME
    journal.write_text("{}", encoding="utf-8")
    transaction = _transaction(
        parent_identity=output_reconciliation.path_identity(tmp_path),
        transaction_identity=output_reconciliation.path_identity(coordinator),
        journal_identity=output_reconciliation.path_identity(journal),
        phase="terminal",
    )
    state = output_reconciliation._JournalState(
        transaction=transaction,
        generation=1,
        record_hash="sha256:" + ("0" * 64),
        valid_length=2,
        has_partial_tail=False,
    )

    assert output_reconciliation._journal_only_cleanup_lock_may_create(
        coordinator,
        state,
        journal,
    )
    assert not output_reconciliation._journal_only_cleanup_lock_may_create(
        tmp_path / "wrong-name",
        state,
        journal,
    )
    (coordinator / "foreign").touch()
    with pytest.raises(ValueError, match="reconcile_transaction_cleanup_invalid"):
        output_reconciliation._journal_only_cleanup_lock_may_create(
            coordinator,
            state,
            journal,
        )


def test_approval_manifest_handles_absent_and_changed_live_roots(tmp_path: Path) -> None:
    root = tmp_path / "outputs"
    absent = _transaction(
        outputs_name="outputs",
        parent_identity=output_reconciliation.path_identity(tmp_path),
        live_identity=None,
    )
    output_reconciliation._require_approval_manifest_current(root, absent)
    root.mkdir()
    with pytest.raises(ValueError, match="reconcile_output_root_changed"):
        output_reconciliation._require_approval_manifest_current(root, absent)

    changed = replace(absent, live_identity=OTHER_IDENTITY)
    with pytest.raises(ValueError, match="reconcile_output_root_changed"):
        output_reconciliation._require_approval_manifest_current(root, changed)


def test_plain_json_rejects_hardlinks_and_malformed_documents(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    alias = tmp_path / "alias.json"
    os.link(source, alias)
    with pytest.raises(ValueError, match="reconcile_json_file_unsafe"):
        output_reconciliation._read_plain_json(source)

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="reconcile_json_invalid"):
        output_reconciliation._read_plain_json(malformed)
    with pytest.raises(ValueError, match="reconcile_directory_unreadable"):
        output_reconciliation._plain_scandir(malformed)


def _journal_state(
    transaction: output_reconciliation._RootTransaction,
) -> output_reconciliation._JournalState:
    return output_reconciliation._JournalState(
        transaction=transaction,
        generation=1,
        record_hash="sha256:" + ("0" * 64),
        valid_length=1,
        has_partial_tail=False,
    )


@pytest.mark.parametrize(
    ("transaction", "identities", "inventory_current", "reason"),
    [
        (
            _transaction(phase="staged_ready"),
            {"outputs": (99, 99, 99), "previous": None},
            True,
            "reconcile_transaction_live_move_invalid",
        ),
        (
            _transaction(phase="staged_ready", live_identity=None),
            {"outputs": IDENTITY},
            True,
            "reconcile_transaction_live_move_invalid",
        ),
        (
            _transaction(phase="previous_moved"),
            {"staged": IDENTITY, "outputs": None},
            True,
            "reconcile_transaction_staged_move_invalid",
        ),
        (
            _transaction(phase="building"),
            {},
            True,
            "reconcile_transaction_phase_invalid",
        ),
        (
            _transaction(phase="live_committed"),
            {"outputs": IDENTITY},
            True,
            "reconcile_transaction_live_identity_invalid",
        ),
        (
            _transaction(phase="live_committed"),
            {"outputs": OTHER_IDENTITY},
            False,
            "reconcile_final_inventory_invalid",
        ),
    ],
    ids=(
        "live-move-ambiguous",
        "unexpected-live-root",
        "staged-move-ambiguous",
        "wrong-phase",
        "wrong-live-identity",
        "invalid-final-inventory",
    ),
)
def test_continue_root_transaction_rejects_each_recovery_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    transaction: output_reconciliation._RootTransaction,
    identities: dict[str, tuple[int, int, int] | None],
    inventory_current: bool,
    reason: str,
) -> None:
    root = tmp_path / "outputs"
    journal_path = tmp_path / "transaction" / output_reconciliation._ROOT_JOURNAL_NAME
    monkeypatch.setattr(
        output_reconciliation,
        "_path_identity_or_none",
        lambda path: identities.get(path.name),
    )
    monkeypatch.setattr(
        output_reconciliation,
        "_require_staged_authority",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        output_reconciliation,
        "_require_approval_manifest_current",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        output_reconciliation,
        "_scan_inventory",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        output_reconciliation,
        "_inventory_is_current",
        lambda _inventory: inventory_current,
    )

    class Guard:
        def validate(self) -> None:
            return None

    with pytest.raises(ValueError, match=reason):
        output_reconciliation._continue_root_transaction(
            root,
            _authority("Deck"),
            _journal_state(transaction),
            journal_path=journal_path,
            parent_guard=Guard(),
            fault_hook=output_reconciliation.no_fault,
        )


def test_deletion_and_render_helpers_reject_changed_physical_truth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "outputs"
    deck = root / "Deck"
    deck.mkdir(parents=True)
    payload = deck / "payload.json"
    payload.write_text("{}", encoding="utf-8")
    nodes = output_reconciliation._capture_plain_tree(deck)
    entry = output_reconciliation._DeletionEntry(
        path=deck,
        relative_root="Deck",
        identity=output_reconciliation.path_identity(deck),
        deck_name="Deck",
        nodes=nodes,
        tree_sha256=output_reconciliation._tree_content_sha256(nodes),
    )

    (root / "extra").mkdir()
    with pytest.raises(ValueError, match="reconcile_output_root_changed"):
        output_reconciliation._require_deletion_manifest_unchanged(root, (entry,))
    (root / "extra").rmdir()

    changed = replace(entry, identity=OTHER_IDENTITY)
    with pytest.raises(ValueError, match="reconcile_deletion_identity_changed"):
        output_reconciliation._remove_manifest_entry(changed)

    monkeypatch.setattr(
        output_reconciliation,
        "render_all_audited_configure_runs",
        lambda _path: {},
    )
    with pytest.raises(ValueError, match="reconcile_rendered_deck_set_invalid"):
        output_reconciliation._build_rendered_audited_runs(_authority("Deck"))

    with pytest.raises(ValueError, match="reconcile_rendered_output_invalid"):
        output_reconciliation._require_complete_rendered_set(
            {"Deck": object()},
            _authority("Deck"),
        )


def test_plain_tree_rejects_reparse_and_detects_root_identity_change(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "payload").write_text("x", encoding="utf-8")

    monkeypatch.setattr(output_reconciliation, "_status_is_reparse", lambda _status: True)
    with pytest.raises(ValueError, match="reconcile_deletion_reparse"):
        output_reconciliation._capture_plain_tree(root)

    monkeypatch.setattr(output_reconciliation, "_status_is_reparse", lambda _status: False)
    real_identity = output_reconciliation.path_identity
    calls = 0

    def changing_identity(path: Path) -> tuple[int, int, int]:
        nonlocal calls
        calls += 1
        identity = real_identity(path)
        return identity if calls == 1 else OTHER_IDENTITY

    monkeypatch.setattr(output_reconciliation, "path_identity", changing_identity)
    with pytest.raises(ValueError, match="reconcile_deletion_identity_changed"):
        output_reconciliation._capture_plain_tree(root)
