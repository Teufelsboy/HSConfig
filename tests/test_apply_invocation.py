from __future__ import annotations

import ast
import inspect
import json
import os
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from queue import Queue
from threading import Thread
from typing import Iterator
from unittest.mock import patch

import pytest

from hsconfig import apply_invocation as apply_invocation_module
from hsconfig.apply_invocation import (
    APPLY_INVOCATION_FIELDS,
    APPLY_INVOCATION_MAX_BYTES,
    APPLY_INVOCATION_SCHEMA_VERSION,
    PRE_APPLY_DECK_NAME_MAX_CHARS,
    PRE_APPLY_RUNTIME_SNAPSHOT_FIELDS,
    PRE_APPLY_TRANSACTION_IDS_ADMISSION_MAX,
    PRE_APPLY_TRANSACTION_IDS_MAX,
    ApplyInvocation,
    PreApplyRuntimeSnapshot,
    ValidatedSameAttemptJournalDelta,
    build_apply_invocation,
    build_pre_apply_runtime_snapshot,
    capture_pre_apply_runtime_snapshot,
    load_apply_invocation,
    parse_apply_invocation,
    require_apply_invocation_admission_capacity,
    require_same_attempt_pre_apply_snapshot,
)
from hsconfig.operator_profile import (
    OperatorProfileLease,
    enable_operator_profile,
    lease_operator_profile,
)
from hsconfig.package_io import path_identity


def _digest(character: str) -> str:
    return "sha256:" + character * 64


@contextmanager
def _runtime_profile_lease(
    tmp_path: Path,
    runtime_root: Path,
) -> Iterator[OperatorProfileLease]:
    local_app_data = tmp_path / "local-app-data"
    output_base_root = tmp_path / "profile-output"
    local_app_data.mkdir(parents=True, exist_ok=True)
    output_base_root.mkdir(parents=True, exist_ok=True)
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        profile = enable_operator_profile(
            runtime_root=runtime_root,
            output_base_root=output_base_root,
            expected_predecessor_sha256=None,
        )
        with lease_operator_profile(expected_profile=profile) as lease:
            yield lease


def _snapshot(
    *,
    transaction_ids: tuple[str, ...] = (),
) -> PreApplyRuntimeSnapshot:
    return build_pre_apply_runtime_snapshot(
        deck_name="ShadowPriest",
        mapping_value="shadowpriest--sha256-" + "a" * 64,
        deck_config_ini_sha256=_digest("1"),
        runtime_state_sha256=_digest("2"),
        last_apply_receipt_sha256=_digest("3"),
        runtime_tree_sha256=_digest("4"),
        transaction_ids=transaction_ids,
    )


def _invocation(
    tmp_path: Path,
    *,
    snapshot: PreApplyRuntimeSnapshot | None = None,
    run_id: str = "b" * 32,
    runtime_root: Path | None = None,
    runtime_root_identity: tuple[int, int, int] | None = None,
    output_operation_admission_path: Path | None = None,
    output_operation_admission_identity: tuple[int, int, int] | None = None,
    output_operation_admission_sha256: str | None = None,
    output_child_binding_sha256: str | None = None,
    output_child_path: Path | None = None,
    output_child_identity: tuple[int, int, int] | None = None,
    operator_profile_sha256: str | None = None,
    publication_revision: str | None = None,
    publication_content_root_sha256: str | None = None,
) -> ApplyInvocation:
    runtime_root = tmp_path / "runtime" if runtime_root is None else runtime_root
    output_child = (
        tmp_path / "output" / "ShadowPriest"
        if output_child_path is None
        else output_child_path
    )
    operation = (
        tmp_path / "state" / "output-operation-admission.json"
        if output_operation_admission_path is None
        else output_operation_admission_path
    )
    for directory in (runtime_root, output_child, operation.parent):
        directory.mkdir(parents=True, exist_ok=True)
    if not operation.exists():
        operation.write_bytes(b"operation\n")
    return build_apply_invocation(
        apply_attempt_id="a" * 32,
        run_id=run_id,
        publication_revision=(
            "revisions/sha256-" + "c" * 64
            if publication_revision is None
            else publication_revision
        ),
        publication_content_root_sha256=(
            _digest("c")
            if publication_content_root_sha256 is None
            else publication_content_root_sha256
        ),
        output_operation_admission_path=operation,
        output_operation_admission_identity=(
            path_identity(operation)
            if output_operation_admission_identity is None
            else output_operation_admission_identity
        ),
        output_operation_admission_sha256=(
            _digest("d")
            if output_operation_admission_sha256 is None
            else output_operation_admission_sha256
        ),
        output_child_binding_sha256=(
            _digest("e")
            if output_child_binding_sha256 is None
            else output_child_binding_sha256
        ),
        output_child_path=output_child,
        output_child_identity=(
            path_identity(output_child)
            if output_child_identity is None
            else output_child_identity
        ),
        operator_profile_sha256=(
            _digest("f")
            if operator_profile_sha256 is None
            else operator_profile_sha256
        ),
        runtime_root=runtime_root,
        runtime_root_identity=(
            path_identity(runtime_root)
            if runtime_root_identity is None
            else runtime_root_identity
        ),
        pre_apply_runtime_snapshot=_snapshot() if snapshot is None else snapshot,
    )


def test_apply_invocation_has_exact_closed_canonical_schema(
    tmp_path: Path,
) -> None:
    invocation = _invocation(tmp_path)
    document = json.loads(invocation.canonical_json)

    assert APPLY_INVOCATION_SCHEMA_VERSION == 1
    assert APPLY_INVOCATION_MAX_BYTES == 128 * 1024
    assert PRE_APPLY_TRANSACTION_IDS_MAX == 128
    assert PRE_APPLY_TRANSACTION_IDS_ADMISSION_MAX == 127
    assert PRE_APPLY_DECK_NAME_MAX_CHARS == 128
    expected_invocation_fields = frozenset(
        {
            "schema_version",
            "apply_attempt_id",
            "run_id",
            "publication_revision",
            "publication_content_root_sha256",
            "output_operation_admission_path",
            "output_operation_admission_identity",
            "output_operation_admission_sha256",
            "output_child_binding_sha256",
            "output_child_path",
            "output_child_identity",
            "operator_profile_sha256",
            "runtime_root",
            "runtime_root_identity",
            "pre_apply_runtime_snapshot",
            "content_sha256",
        }
    )
    expected_snapshot_fields = frozenset(
        {
            "deck_name",
            "mapping_value",
            "deck_config_ini_sha256",
            "runtime_state_sha256",
            "last_apply_receipt_sha256",
            "runtime_tree_sha256",
            "transaction_ids",
            "content_sha256",
        }
    )
    assert APPLY_INVOCATION_FIELDS == expected_invocation_fields
    assert PRE_APPLY_RUNTIME_SNAPSHOT_FIELDS == expected_snapshot_fields
    assert set(document) == expected_invocation_fields
    assert set(document["pre_apply_runtime_snapshot"]) == expected_snapshot_fields
    assert invocation.canonical_json == (
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    ).encode("utf-8")
    unsigned = dict(document)
    content_sha256 = unsigned.pop("content_sha256")
    assert content_sha256 == _canonical_digest(unsigned)
    nested_unsigned = dict(document["pre_apply_runtime_snapshot"])
    nested_digest = nested_unsigned.pop("content_sha256")
    assert nested_digest == _canonical_digest(nested_unsigned)
    assert parse_apply_invocation(invocation.canonical_json) == invocation


def test_pre_apply_snapshot_binds_mapping_ini_state_receipt_tree_and_transactions(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    active = runtime_root / "CustomConfig" / "shadow-v1"
    transactions = runtime_root / ".hsconfig" / "transactions"
    receipt = runtime_root / ".hsconfig" / "receipts" / "shadow" / "last_apply_receipt.json"
    active.mkdir(parents=True)
    transactions.mkdir(parents=True)
    receipt.parent.mkdir(parents=True)
    (runtime_root / "CustomConfig" / "deck_config.ini").write_text(
        "[OTHER]\nShadowPriest = ignored\n[CONFIGS]\nShadowPriest = shadow-v1\n",
        encoding="utf-8",
    )
    (runtime_root / ".hsconfig" / "state.json").write_bytes(b'{"state":1}\n')
    receipt.write_bytes(b'{"receipt":1}\n')
    (active / "Card.json").write_bytes(b'{"card":1}\n')
    (active / "nested").mkdir()
    (active / "nested" / "Extra.ini").write_bytes(b"alpha\r\n")
    for transaction_id in ("b" * 32, "a" * 32):
        (transactions / f"{transaction_id}.json").write_bytes(b"{}\n")

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        captured = capture_pre_apply_runtime_snapshot(
            runtime_root=runtime_root,
            expected_runtime_root_identity=path_identity(runtime_root),
            deck_name="ShadowPriest",
            state_key="shadow",
            profile_lease=profile_lease,
        )

    assert captured.mapping_value == "shadow-v1"
    assert captured.deck_config_ini_sha256 == _file_digest(
        runtime_root / "CustomConfig" / "deck_config.ini"
    )
    assert captured.runtime_state_sha256 == _file_digest(
        runtime_root / ".hsconfig" / "state.json"
    )
    assert captured.last_apply_receipt_sha256 == _file_digest(receipt)
    assert captured.runtime_tree_sha256 == (
        "sha256:0fb9b1e5b0a1365a9710273966242f7b1bb6bfa36b9916b0d08a5bb12fbc98e5"
    )
    assert captured.transaction_ids == ("a" * 32, "b" * 32)
    first_tree_digest = captured.runtime_tree_sha256
    (active / "Card.json").write_bytes(b'{"card":2}\n')
    with _runtime_profile_lease(
        tmp_path / "changed-profile",
        runtime_root,
    ) as profile_lease:
        changed = capture_pre_apply_runtime_snapshot(
            runtime_root=runtime_root,
            expected_runtime_root_identity=path_identity(runtime_root),
            deck_name="ShadowPriest",
            state_key="shadow",
            profile_lease=profile_lease,
        )
    assert changed.runtime_tree_sha256 not in {None, first_tree_digest}


def test_runtime_snapshot_treats_missing_mapped_tree_as_null_without_creating_it(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    custom_config = runtime_root / "CustomConfig"
    custom_config.mkdir(parents=True)
    (custom_config / "deck_config.ini").write_text(
        "[CONFIGS]\nShadowPriest = missing-active-tree\n",
        encoding="utf-8",
    )
    missing_tree = custom_config / "missing-active-tree"

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        captured = capture_pre_apply_runtime_snapshot(
            runtime_root=runtime_root,
            expected_runtime_root_identity=path_identity(runtime_root),
            deck_name="ShadowPriest",
            state_key="shadow",
            profile_lease=profile_lease,
        )

    assert captured.mapping_value == "missing-active-tree"
    assert captured.runtime_tree_sha256 is None
    assert not missing_tree.exists()


def test_apply_invocation_rejects_wrong_types_unknown_fields_size_or_self_digest(
    tmp_path: Path,
) -> None:
    document = json.loads(_invocation(tmp_path).canonical_json)
    invalid_documents: list[object] = []
    for field, value in (
        ("schema_version", True),
        ("apply_attempt_id", 1),
        ("runtime_root_identity", [True, 2, 3]),
    ):
        changed = dict(document)
        changed[field] = value
        _reseal(changed)
        invalid_documents.append(changed)
    unknown = dict(document)
    unknown["unknown"] = None
    _reseal(unknown)
    invalid_documents.append(unknown)
    wrong_digest = dict(document)
    wrong_digest["content_sha256"] = _digest("0")
    invalid_documents.append(wrong_digest)
    invalid_documents.append([document])

    for invalid in invalid_documents:
        with pytest.raises((TypeError, ValueError)):
            parse_apply_invocation(_json_bytes(invalid))
    with pytest.raises(ValueError, match="too_large"):
        parse_apply_invocation(b" " * (APPLY_INVOCATION_MAX_BYTES + 1))
    duplicate = (
        b'{"apply_attempt_id":"'
        + _invocation(tmp_path).apply_attempt_id.encode("ascii")
        + b'",'
        + _invocation(tmp_path).canonical_json[1:]
    )
    with pytest.raises(ValueError, match="duplicate"):
        parse_apply_invocation(duplicate)
    non_finite = _invocation(tmp_path).canonical_json.replace(
        b'"schema_version":1',
        b'"schema_version":NaN',
    )
    with pytest.raises(ValueError, match="non_finite"):
        parse_apply_invocation(non_finite)


def test_apply_invocation_builder_and_parser_share_exact_size_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _invocation(tmp_path / "reference")
    exact_size = len(reference.canonical_json)
    monkeypatch.setattr(
        apply_invocation_module,
        "APPLY_INVOCATION_MAX_BYTES",
        exact_size,
    )

    exact = _invocation(tmp_path / "reference")
    assert len(exact.canonical_json) == exact_size
    assert parse_apply_invocation(exact.canonical_json) == exact

    monkeypatch.setattr(
        apply_invocation_module,
        "APPLY_INVOCATION_MAX_BYTES",
        exact_size - 1,
    )
    with pytest.raises(ValueError, match="too_large"):
        _invocation(tmp_path / "reference")
    with pytest.raises(ValueError, match="too_large"):
        parse_apply_invocation(exact.canonical_json)


def test_apply_invocation_converts_deep_json_recursion_to_typed_value_error() -> None:
    deeply_nested = b"[" * 2_000 + b"0" + b"]" * 2_000

    with pytest.raises(ValueError, match="json_invalid"):
        parse_apply_invocation(deeply_nested)


def test_load_apply_invocation_rejects_parent_replacement_after_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation = _invocation(tmp_path / "source")
    parent = tmp_path / "invocations"
    parent.mkdir()
    path = parent / "apply-invocation.json"
    path.write_bytes(invocation.canonical_json)
    expected_parent_identity = path_identity(parent)
    real_read = apply_invocation_module.read_file_no_follow

    def replace_parent_after_read(*args: object, **kwargs: object) -> bytes:
        content = real_read(*args, **kwargs)
        parent.rename(tmp_path / "old-invocations")
        parent.mkdir()
        path.write_bytes(content)
        return content

    monkeypatch.setattr(
        apply_invocation_module,
        "read_file_no_follow",
        replace_parent_after_read,
    )
    with pytest.raises(
        ValueError,
        match="filesystem_path_identity_changed|parent_identity",
    ):
        load_apply_invocation(
            path,
            expected_parent_identity=expected_parent_identity,
        )


def test_load_apply_invocation_rejects_parent_replacement_during_parse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation = _invocation(tmp_path / "source")
    parent = tmp_path / "invocations"
    parent.mkdir()
    path = parent / "apply-invocation.json"
    path.write_bytes(invocation.canonical_json)
    expected_parent_identity = path_identity(parent)
    real_parse = apply_invocation_module.parse_apply_invocation

    def replace_parent_during_parse(content: bytes) -> ApplyInvocation:
        parsed = real_parse(content)
        parent.rename(tmp_path / "old-invocations")
        parent.mkdir()
        path.write_bytes(content)
        return parsed

    monkeypatch.setattr(
        apply_invocation_module,
        "parse_apply_invocation",
        replace_parent_during_parse,
    )
    with pytest.raises(
        ValueError,
        match="filesystem_path_identity_changed|parent_identity",
    ):
        load_apply_invocation(
            path,
            expected_parent_identity=expected_parent_identity,
        )


def test_apply_invocation_rejects_every_missing_required_field_and_nested_duplicate(
    tmp_path: Path,
) -> None:
    document = json.loads(_invocation(tmp_path).canonical_json)
    for field in tuple(document):
        changed = dict(document)
        changed.pop(field)
        if field != "content_sha256":
            _reseal(changed)
        with pytest.raises(ValueError):
            parse_apply_invocation(_json_bytes(changed))

    snapshot = dict(document["pre_apply_runtime_snapshot"])
    for field in tuple(snapshot):
        changed_snapshot = dict(snapshot)
        changed_snapshot.pop(field)
        if field != "content_sha256":
            _reseal(changed_snapshot)
        changed = dict(document)
        changed["pre_apply_runtime_snapshot"] = changed_snapshot
        _reseal(changed)
        with pytest.raises(ValueError):
            parse_apply_invocation(_json_bytes(changed))

    needle = b'"deck_name":"ShadowPriest"'
    canonical = _invocation(tmp_path / "duplicate").canonical_json
    assert canonical.count(needle) == 1
    nested_duplicate = canonical.replace(needle, needle + b"," + needle, 1)
    with pytest.raises(ValueError, match="duplicate"):
        parse_apply_invocation(nested_duplicate)


def test_apply_invocation_enforces_all_path_digest_text_and_list_boundaries(
    tmp_path: Path,
) -> None:
    invocation = _invocation(tmp_path)
    document = json.loads(invocation.canonical_json)
    changes: tuple[tuple[str, object], ...] = (
        ("run_id", "A" * 32),
        ("apply_attempt_id", "a" * 31),
        ("publication_revision", "sha256-" + "c" * 64),
        ("publication_content_root_sha256", "c" * 64),
        ("output_operation_admission_path", "relative.json"),
        ("output_operation_admission_identity", [1, 2]),
        ("output_operation_admission_sha256", "sha256:" + "A" * 64),
        ("output_child_binding_sha256", "sha256:" + "A" * 64),
        ("output_child_path", str(invocation.output_child_path / "..")),
        ("output_child_identity", [1, True, 3]),
        ("runtime_root", str(invocation.runtime_root) + os.sep + "."),
        ("runtime_root_identity", [-1, 2, 3]),
        ("operator_profile_sha256", "sha256:" + "A" * 64),
    )
    for field, value in changes:
        changed = dict(document)
        changed[field] = value
        _reseal(changed)
        with pytest.raises(ValueError):
            parse_apply_invocation(_json_bytes(changed))

    nested = dict(document["pre_apply_runtime_snapshot"])
    nested["deck_name"] = "x" * (PRE_APPLY_DECK_NAME_MAX_CHARS + 1)
    _reseal(nested)
    changed = dict(document)
    changed["pre_apply_runtime_snapshot"] = nested
    _reseal(changed)
    with pytest.raises(ValueError):
        parse_apply_invocation(_json_bytes(changed))
    nested_cases: tuple[tuple[str, object], ...] = (
        ("deck_name", ""),
        ("deck_name", "Deck\nName"),
        ("mapping_value", "../unsafe"),
        ("deck_config_ini_sha256", "1" * 64),
        ("runtime_state_sha256", "sha256:" + "A" * 64),
        ("last_apply_receipt_sha256", 1),
        ("runtime_tree_sha256", False),
        ("transaction_ids", ["b" * 32, "a" * 32]),
        ("transaction_ids", ["a" * 31]),
        (
            "transaction_ids",
            [f"{index:032x}" for index in range(PRE_APPLY_TRANSACTION_IDS_MAX + 1)],
        ),
    )
    for field, value in nested_cases:
        nested = dict(document["pre_apply_runtime_snapshot"])
        nested[field] = value
        _reseal(nested)
        changed = dict(document)
        changed["pre_apply_runtime_snapshot"] = nested
        _reseal(changed)
        with pytest.raises((TypeError, ValueError)):
            parse_apply_invocation(_json_bytes(changed))

    nested_unknown = dict(document["pre_apply_runtime_snapshot"])
    nested_unknown["unknown"] = None
    _reseal(nested_unknown)
    changed = dict(document)
    changed["pre_apply_runtime_snapshot"] = nested_unknown
    _reseal(changed)
    with pytest.raises(ValueError):
        parse_apply_invocation(_json_bytes(changed))
    nested_bad_digest = dict(document["pre_apply_runtime_snapshot"])
    nested_bad_digest["content_sha256"] = _digest("0")
    changed = dict(document)
    changed["pre_apply_runtime_snapshot"] = nested_bad_digest
    _reseal(changed)
    with pytest.raises(ValueError):
        parse_apply_invocation(_json_bytes(changed))

    maximal_snapshot = build_pre_apply_runtime_snapshot(
        deck_name="D" * PRE_APPLY_DECK_NAME_MAX_CHARS,
        mapping_value=None,
        deck_config_ini_sha256=None,
        runtime_state_sha256=None,
        last_apply_receipt_sha256=None,
        runtime_tree_sha256=None,
        transaction_ids=tuple(
            f"{index:032x}" for index in range(PRE_APPLY_TRANSACTION_IDS_MAX)
        ),
    )
    maximal = _invocation(tmp_path / "maximal", snapshot=maximal_snapshot)
    assert parse_apply_invocation(maximal.canonical_json) == maximal
    for suffix in (b"\n", b" ", b"\r\n"):
        with pytest.raises(ValueError, match="canonical"):
            parse_apply_invocation(maximal.canonical_json + suffix)

    duplicate = dict(document["pre_apply_runtime_snapshot"])
    duplicate["transaction_ids"] = ["a" * 32, "a" * 32]
    _reseal(duplicate)
    changed = dict(document)
    changed["pre_apply_runtime_snapshot"] = duplicate
    _reseal(changed)
    with pytest.raises(ValueError):
        parse_apply_invocation(_json_bytes(changed))


@pytest.mark.parametrize(
    "mapping_value",
    (
        "CON",
        "con.txt",
        "NUL.txt",
        "runtime.",
        "runtime ",
        "COM¹",
        "COM².txt",
        "LPT³",
        "lpt¹.json",
    ),
)
def test_pre_apply_snapshot_rejects_windows_unsafe_runtime_components(
    mapping_value: str,
) -> None:
    with pytest.raises(ValueError, match="mapping_value"):
        build_pre_apply_runtime_snapshot(
            deck_name="ShadowPriest",
            mapping_value=mapping_value,
            deck_config_ini_sha256=None,
            runtime_state_sha256=None,
            last_apply_receipt_sha256=None,
            runtime_tree_sha256=None,
            transaction_ids=(),
        )


def test_pre_apply_snapshot_accepts_safe_unicode_runtime_component() -> None:
    snapshot = build_pre_apply_runtime_snapshot(
        deck_name="ShadowPriest",
        mapping_value="prêtre-影子.v1",
        deck_config_ini_sha256=None,
        runtime_state_sha256=None,
        last_apply_receipt_sha256=None,
        runtime_tree_sha256=None,
        transaction_ids=(),
    )

    assert snapshot.mapping_value == "prêtre-影子.v1"


def test_runtime_snapshot_is_read_only_when_runtime_metadata_is_absent(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    before = tuple(runtime_root.iterdir())

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        captured = capture_pre_apply_runtime_snapshot(
            runtime_root=runtime_root,
            expected_runtime_root_identity=path_identity(runtime_root),
            deck_name="ShadowPriest",
            state_key="shadow",
            profile_lease=profile_lease,
        )

    assert tuple(runtime_root.iterdir()) == before == ()
    assert captured.mapping_value is None
    assert captured.deck_config_ini_sha256 is None
    assert captured.runtime_state_sha256 is None
    assert captured.last_apply_receipt_sha256 is None
    assert captured.runtime_tree_sha256 is None
    assert captured.transaction_ids == ()


def test_runtime_snapshot_requires_active_root_bound_profile_lease(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    other_runtime_root = tmp_path / "other-runtime"
    runtime_root.mkdir()
    other_runtime_root.mkdir()

    with pytest.raises(TypeError, match="profile_lease"):
        capture_pre_apply_runtime_snapshot(
            runtime_root=runtime_root,
            expected_runtime_root_identity=path_identity(runtime_root),
            deck_name="ShadowPriest",
            state_key="shadow",
        )
    with pytest.raises(TypeError, match="operator_profile_lease_required"):
        capture_pre_apply_runtime_snapshot(
            runtime_root=runtime_root,
            expected_runtime_root_identity=path_identity(runtime_root),
            deck_name="ShadowPriest",
            state_key="shadow",
            profile_lease=object(),
        )

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        stale_lease = profile_lease
        with pytest.raises(ValueError, match="profile_binding"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=other_runtime_root,
                expected_runtime_root_identity=path_identity(other_runtime_root),
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )

        observed: Queue[BaseException | None] = Queue()

        def cross_thread_capture() -> None:
            try:
                capture_pre_apply_runtime_snapshot(
                    runtime_root=runtime_root,
                    expected_runtime_root_identity=path_identity(runtime_root),
                    deck_name="ShadowPriest",
                    state_key="shadow",
                    profile_lease=profile_lease,
                )
            except BaseException as error:
                observed.put(error)
            else:
                observed.put(None)

        worker = Thread(target=cross_thread_capture)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive()
        cross_thread_error = observed.get_nowait()
        assert isinstance(cross_thread_error, ValueError)
        assert "wrong_thread" in str(cross_thread_error)

    with pytest.raises(ValueError, match="inactive"):
        capture_pre_apply_runtime_snapshot(
            runtime_root=runtime_root,
            expected_runtime_root_identity=path_identity(runtime_root),
            deck_name="ShadowPriest",
            state_key="shadow",
            profile_lease=stale_lease,
        )


def test_runtime_snapshot_revalidates_profile_after_full_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    real_capture_transaction_ids = apply_invocation_module._capture_transaction_ids

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:

        def mutate_profile_after_last_snapshot_read(root: Path) -> tuple[str, ...]:
            identifiers = real_capture_transaction_ids(root)
            profile_lease.profile_path.write_bytes(
                profile_lease.profile_path.read_bytes() + b"\n"
            )
            return identifiers

        monkeypatch.setattr(
            apply_invocation_module,
            "_capture_transaction_ids",
            mutate_profile_after_last_snapshot_read,
        )
        with pytest.raises(ValueError, match="operator_profile"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=runtime_root,
                expected_runtime_root_identity=path_identity(runtime_root),
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )


def test_runtime_snapshot_has_no_layout_planner_recovery_or_mutation_callgraph() -> None:
    tree = ast.parse(inspect.getsource(apply_invocation_module))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden_modules = {
        "hsconfig.live_start_session",
        "hsconfig.published_apply",
        "hsconfig.runtime_installer",
        "hsconfig.runtime_transaction_journal",
    }
    assert imported_modules.isdisjoint(forbidden_modules)

    call_names = {
        node.func.id
        if isinstance(node.func, ast.Name)
        else node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    forbidden_calls = {
        "_ensure_runtime_layout",
        "_recover_locked",
        "atomic_write_bytes",
        "install_runtime_package",
        "mkdir",
        "plan_runtime_install",
        "recover_runtime_state",
        "secure_create_directory",
        "secure_replace",
        "secure_unlink",
    }
    assert call_names.isdisjoint(forbidden_calls)


def test_runtime_snapshot_rejects_wrong_or_replaced_runtime_root_identity(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    original_identity = path_identity(runtime_root)
    wrong_identity = (
        original_identity[0],
        original_identity[1] + 1,
        original_identity[2],
    )

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        with pytest.raises(ValueError, match="runtime_root_identity_changed"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=runtime_root,
                expected_runtime_root_identity=wrong_identity,
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )

        runtime_root.rename(tmp_path / "original-runtime")
        runtime_root.mkdir()
        assert path_identity(runtime_root) != original_identity
        with pytest.raises(ValueError, match="runtime_root_identity_changed"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=runtime_root,
                expected_runtime_root_identity=original_identity,
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )


def test_runtime_snapshot_rejects_hardlinked_active_tree_file(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    active = runtime_root / "CustomConfig" / "shadow-v1"
    active.mkdir(parents=True)
    (runtime_root / "CustomConfig" / "deck_config.ini").write_text(
        "[CONFIGS]\nShadowPriest = shadow-v1\n",
        encoding="utf-8",
    )
    source = active / "Card.json"
    source.write_bytes(b"{}\n")
    os.link(source, active / "Alias.json")

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        with pytest.raises(ValueError, match="filesystem_tree_entry_invalid"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=runtime_root,
                expected_runtime_root_identity=path_identity(runtime_root),
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )


def test_runtime_snapshot_rejects_reparse_active_tree_when_supported(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    custom_config = runtime_root / "CustomConfig"
    custom_config.mkdir(parents=True)
    (custom_config / "deck_config.ini").write_text(
        "[CONFIGS]\nShadowPriest = shadow-v1\n",
        encoding="utf-8",
    )
    target = tmp_path / "target"
    target.mkdir()
    (target / "Card.json").write_bytes(b"{}\n")
    try:
        os.symlink(target, custom_config / "shadow-v1", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        with pytest.raises(ValueError, match="filesystem_ancestor_reparse"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=runtime_root,
                expected_runtime_root_identity=path_identity(runtime_root),
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )


@pytest.mark.parametrize(
    "entry_name",
    (
        "foreign.json",
        f"{'a' * 32}.json.tmp",
    ),
)
def test_runtime_snapshot_rejects_foreign_or_temp_transaction_entries(
    tmp_path: Path,
    entry_name: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    transactions = runtime_root / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    (transactions / entry_name).write_bytes(b"{}\n")

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        with pytest.raises(ValueError, match="transaction_inventory_invalid"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=runtime_root,
                expected_runtime_root_identity=path_identity(runtime_root),
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )


def test_runtime_snapshot_allows_128_transactions_and_rejects_the_129th(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    transactions = runtime_root / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    expected_ids = tuple(f"{index:032x}" for index in range(128))
    for transaction_id in expected_ids:
        (transactions / f"{transaction_id}.json").write_bytes(b"{}\n")

    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        captured = capture_pre_apply_runtime_snapshot(
            runtime_root=runtime_root,
            expected_runtime_root_identity=path_identity(runtime_root),
            deck_name="ShadowPriest",
            state_key="shadow",
            profile_lease=profile_lease,
        )
        assert captured.transaction_ids == expected_ids

        (transactions / f"{128:032x}.json").write_bytes(b"{}\n")
        with pytest.raises(ValueError, match="transaction_inventory_limit"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=runtime_root,
                expected_runtime_root_identity=path_identity(runtime_root),
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )


def test_runtime_snapshot_rejects_transaction_membership_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root = tmp_path / "runtime"
    transactions = runtime_root / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    first = transactions / f"{'1' * 32}.json"
    successor = transactions / f"{'2' * 32}.json"
    first.write_bytes(b"{}\n")
    real_scandir = os.scandir
    transaction_scans = 0

    def drifting_scandir(path: os.PathLike[str] | str) -> os.ScandirIterator[str]:
        nonlocal transaction_scans
        if Path(path) == transactions:
            transaction_scans += 1
            if transaction_scans == 2:
                first.unlink()
                successor.write_bytes(b"{}\n")
        return real_scandir(path)

    monkeypatch.setattr(apply_invocation_module.os, "scandir", drifting_scandir)
    with _runtime_profile_lease(tmp_path, runtime_root) as profile_lease:
        with pytest.raises(ValueError, match="transaction_inventory_changed"):
            capture_pre_apply_runtime_snapshot(
                runtime_root=runtime_root,
                expected_runtime_root_identity=path_identity(runtime_root),
                deck_name="ShadowPriest",
                state_key="shadow",
                profile_lease=profile_lease,
            )
    assert transaction_scans == 2


def test_attempt_id_is_passed_unchanged_to_runtime_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig import runtime_installer

    from tests.test_runtime_installer import publish_fixture

    published, runtime_root, _rendered = publish_fixture(tmp_path / "published")
    plan = runtime_installer.plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    invocation = _invocation(tmp_path / "invocation")
    monkeypatch.setattr(
        runtime_installer.uuid,
        "uuid4",
        lambda: (_ for _ in ()).throw(AssertionError("transaction id regenerated")),
    )

    runtime_installer.install_runtime_package(
        plan,
        transaction_id=invocation.apply_attempt_id,
    )

    transaction_root = runtime_root / ".hsconfig" / "transactions"
    journals = tuple(sorted(transaction_root.glob("*.json")))
    assert journals == (
        transaction_root / f"{invocation.apply_attempt_id}.json",
    )
    loaded = runtime_installer.read_runtime_transaction_journal(journals[0])
    assert loaded.transaction_id == invocation.apply_attempt_id


def test_same_attempt_snapshot_projection_accepts_only_exact_own_journal_delta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_runtime_installer import _genuine_same_attempt_delta_fixture

    with _genuine_same_attempt_delta_fixture(
        tmp_path / "active", monkeypatch
    ) as fixture:
        sealed = fixture.sealed
        current = fixture.current
        attempt_id = fixture.apply_attempt_id
        recovery = fixture.recovery
        assert recovery["predecessor_attempt_record_identity"] != recovery[
            "successor_attempt_record_identity"
        ]
        with pytest.raises(
            ValueError,
            match="^same_attempt_journal_delta_cursor_changed$",
        ):
            fixture.mint(
                expected_attempt_record_identity=tuple(
                    recovery["predecessor_attempt_record_identity"]
                ),
                expected_attempt_record_sha256=str(
                    recovery["predecessor_attempt_record_sha256"]
                ),
            )
        bearer = fixture.mint()
        require_same_attempt_pre_apply_snapshot(
            sealed=sealed,
            current=current,
            apply_attempt_id=attempt_id,
            validated_delta=bearer,
        )
        with pytest.raises(ValueError, match="validated_same_attempt_delta"):
            require_same_attempt_pre_apply_snapshot(
                sealed=sealed,
                current=current,
                apply_attempt_id=attempt_id,
                validated_delta=bearer,
            )

        cross_thread_bearer = fixture.mint()
        observed: Queue[BaseException | None] = Queue()

        def use_on_wrong_thread() -> None:
            try:
                require_same_attempt_pre_apply_snapshot(
                    sealed=sealed,
                    current=current,
                    apply_attempt_id=attempt_id,
                    validated_delta=cross_thread_bearer,
                )
            except BaseException as error:
                observed.put(error)
            else:
                observed.put(None)

        worker = Thread(target=use_on_wrong_thread)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive()
        cross_thread_error = observed.get_nowait()
        assert isinstance(cross_thread_error, ValueError)
        assert "validated_same_attempt_delta" in str(cross_thread_error)
        with pytest.raises(ValueError, match="validated_same_attempt_delta"):
            require_same_attempt_pre_apply_snapshot(
                sealed=sealed,
                current=current,
                apply_attempt_id=attempt_id,
                validated_delta=cross_thread_bearer,
            )

    with _genuine_same_attempt_delta_fixture(
        tmp_path / "expired", monkeypatch
    ) as expired_fixture:
        expired_bearer = expired_fixture.mint()
        expired_sealed = expired_fixture.sealed
        expired_current = expired_fixture.current
        expired_attempt_id = expired_fixture.apply_attempt_id
    with pytest.raises(ValueError, match="validated_same_attempt_delta"):
        require_same_attempt_pre_apply_snapshot(
            sealed=expired_sealed,
            current=expired_current,
            apply_attempt_id=expired_attempt_id,
            validated_delta=expired_bearer,
        )


def test_same_attempt_snapshot_projection_rejects_extra_missing_or_preexisting_attempt_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_runtime_installer import _genuine_same_attempt_delta_fixture

    with _genuine_same_attempt_delta_fixture(tmp_path, monkeypatch) as fixture:
        attempt_id = fixture.apply_attempt_id
        sealed = fixture.sealed
        exact_current = fixture.current
        original_ids = sealed.transaction_ids
        assert exact_current.transaction_ids == tuple(
            sorted((*original_ids, attempt_id))
        )
        bad_lists = (
            (),
            tuple(sorted((*original_ids, attempt_id, "3" * 32))),
            original_ids,
        )
        for transaction_ids in bad_lists:
            current = build_pre_apply_runtime_snapshot(
                **{
                    **sealed.as_build_arguments(),
                    "transaction_ids": transaction_ids,
                }
            )
            bearer = fixture.mint()
            with pytest.raises(
                ValueError,
                match="validated_same_attempt_delta_invalid|snapshot",
            ):
                require_same_attempt_pre_apply_snapshot(
                    sealed=sealed,
                    current=current,
                    apply_attempt_id=attempt_id,
                    validated_delta=bearer,
                )

        non_id_mutations: tuple[tuple[str, object], ...] = (
            ("deck_name", "OtherDeck"),
            ("mapping_value", "other-active-tree"),
            ("deck_config_ini_sha256", _digest("5")),
            ("runtime_state_sha256", _digest("6")),
            ("last_apply_receipt_sha256", _digest("7")),
            ("runtime_tree_sha256", _digest("8")),
        )
        for field, value in non_id_mutations:
            current_arguments = exact_current.as_build_arguments()
            current_arguments[field] = value
            changed_current = build_pre_apply_runtime_snapshot(
                **current_arguments
            )
            bearer = fixture.mint()
            with pytest.raises(ValueError, match="delta|projection|snapshot"):
                require_same_attempt_pre_apply_snapshot(
                    sealed=sealed,
                    current=changed_current,
                    apply_attempt_id=attempt_id,
                    validated_delta=bearer,
                )

    already_sealed = _snapshot(transaction_ids=(attempt_id,))
    with pytest.raises(ValueError, match="snapshot"):
        require_same_attempt_pre_apply_snapshot(
            sealed=already_sealed,
            current=already_sealed,
            apply_attempt_id=attempt_id,
            validated_delta=None,
        )


def test_same_attempt_snapshot_projection_requires_validated_journal_delta_bearer() -> None:
    sealed = _snapshot()
    attempt_id = "2" * 32
    current = build_pre_apply_runtime_snapshot(
        **{**sealed.as_build_arguments(), "transaction_ids": (attempt_id,)}
    )
    blank_forgery = object.__new__(ValidatedSameAttemptJournalDelta)
    distinct_blank_forgery = object.__new__(ValidatedSameAttemptJournalDelta)
    assert blank_forgery != distinct_blank_forgery
    private_bearer = object.__new__(
        apply_invocation_module._SameAttemptDeltaBearer
    )
    private_bearer.active = True
    private_bearer.apply_attempt_id = attempt_id
    private_bearer.sealed_snapshot_sha256 = sealed.content_sha256
    private_bearer.current_snapshot_sha256 = current.content_sha256
    private_bearer.nonce = b"x" * 32
    private_bearer.thread_id = apply_invocation_module.get_ident()
    private_bearer_forgery = object.__new__(ValidatedSameAttemptJournalDelta)
    object.__setattr__(private_bearer_forgery, "_bearer", private_bearer)

    for invalid in (None, True, object(), blank_forgery, private_bearer_forgery):
        with pytest.raises((TypeError, ValueError)):
            require_same_attempt_pre_apply_snapshot(
                sealed=sealed,
                current=current,
                apply_attempt_id=attempt_id,
                validated_delta=invalid,  # type: ignore[arg-type]
            )


def test_apply_admission_reserves_one_transaction_slot_before_runtime_mutation(
    tmp_path: Path,
) -> None:
    invocation = _invocation(
        tmp_path / "full",
        snapshot=_snapshot(
            transaction_ids=tuple(f"{index:032x}" for index in range(128))
        ),
    )
    with pytest.raises(ValueError, match="transaction_capacity"):
        require_apply_invocation_admission_capacity(invocation)

    occupied = _invocation(
        tmp_path / "occupied",
        snapshot=_snapshot(transaction_ids=("a" * 32,)),
    )
    with pytest.raises(ValueError, match="attempt_id"):
        require_apply_invocation_admission_capacity(occupied)

    admitted = _invocation(
        tmp_path / "admitted",
        snapshot=_snapshot(
            transaction_ids=tuple(f"{index:032x}" for index in range(127))
        ),
    )
    require_apply_invocation_admission_capacity(admitted)


def _canonical_digest(value: object) -> str:
    return "sha256:" + sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()


def _reseal(document: dict[str, object]) -> None:
    unsigned = dict(document)
    unsigned.pop("content_sha256", None)
    document["content_sha256"] = _canonical_digest(unsigned)


def _json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _file_digest(path: Path) -> str:
    return "sha256:" + sha256(path.read_bytes()).hexdigest()
