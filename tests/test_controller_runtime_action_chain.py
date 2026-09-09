from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity, status_is_reparse
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    load_runtime_transaction_journals,
    read_runtime_transaction_journal,
    runtime_transaction_journal_path,
)
from tests.test_codex_first_live_e2e import (
    _local_state,
    _matched_package,
    _prepare_approved,
)
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
    _physical_tree,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _sha256_bytes,
    _spawn_and_join,
    _start_apply_entry_observer,
)


_PRE_CAS = (
    LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_PHYSICAL_STEP_BEFORE_CURSOR_CAS
)
_POST_CAS = LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_CURSOR_CAS
_HARD_EXIT = 93


@dataclass(frozen=True, slots=True)
class _ChainAuthority:
    frozen_identity: dict[str, object]
    profile_fingerprint: tuple[tuple[int, int, int], int, str]
    output_root: Path
    publication_tree: dict[str, object]
    attempt_id: str
    apply_invocation_sha256: str
    apply_invocation_fingerprint: tuple[tuple[int, int, int], int, str]
    runtime_admission_binding: dict[str, object]
    runtime_admission_fingerprint: tuple[tuple[int, int, int], int, str]
    runtime_layout_bootstrap: dict[str, object]
    output_operation_admission_binding: dict[str, object]
    output_child_binding: dict[str, object]
    publication_binding: dict[str, object]


def _runtime_tree(
    root: Path,
    *,
    held_lock_path: Path | None,
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for path in (root, *sorted(root.rglob("*"))):
        relative = "." if path == root else path.relative_to(root).as_posix()
        status = path.lstat()
        identity = list(path_identity(path))
        if stat.S_ISDIR(status.st_mode):
            result[relative] = {"kind": "directory", "identity": identity}
        elif stat.S_ISREG(status.st_mode):
            row: dict[str, object] = {
                "kind": "file",
                "identity": identity,
                "size": status.st_size,
            }
            if held_lock_path is not None and path == held_lock_path:
                assert status.st_nlink == 1
                assert status.st_size == 0
                row["sha256"] = None
            else:
                row["sha256"] = _sha256_bytes(path.read_bytes())
            result[relative] = row
        else:
            result[relative] = {"kind": "unsafe", "identity": identity}
    return result


def _normalization_tokens(
    current: session.LiveStartSession,
) -> tuple[tuple[str, str], ...]:
    recovery = current.apply_recovery
    layout = current.runtime_layout_bootstrap
    operation = current.output_operation_admission_binding
    publication = current.publication_binding
    assert isinstance(recovery, Mapping)
    assert isinstance(layout, Mapping)
    assert isinstance(operation, Mapping)
    assert isinstance(publication, Mapping)
    rows = layout["directories"]
    state_receipts = rows[
        session.RUNTIME_LAYOUT_DIRECTORY_ROLES.index("state_receipts")
    ]
    replacements = {
        str(recovery["runtime_root"]): "<runtime-root>",
        str(operation["session_root"]): "<session-root>",
        str(Path(str(operation["session_root"])).parents[2]): "<local-app-data>",
        str(operation["output_child_path"]): "<output-root>",
        str(recovery["apply_attempt_id"]): "<attempt-id>",
        str(current.run_id): "<run-id>",
        Path(str(recovery["candidate_path"])).name: "<candidate-name>",
        Path(str(recovery["renamed_target_path"])).name: "<target-name>",
        Path(str(state_receipts["path"])).name: "<state-key>",
        str(publication["revision"]): "<publication-revision>",
    }
    return tuple(
        sorted(replacements.items(), key=lambda row: len(row[0]), reverse=True)
    )


def _normalized_string(value: str, tokens: tuple[tuple[str, str], ...]) -> str:
    normalized = value.replace("\\", "/")
    for source, target in tokens:
        normalized = normalized.replace(source.replace("\\", "/"), target)
    return normalized


def _semantic_value(
    key: str,
    value: object,
    *,
    tokens: tuple[tuple[str, str], ...],
) -> object:
    if "identity" in key:
        return None if value is None else "BOUND_IDENTITY"
    if "sha256" in key:
        return None if value is None else "BOUND_SHA256"
    if key.endswith("_size"):
        return None if value is None else "BOUND_SIZE"
    if key in {"run_id", "retention_owner_run_id"}:
        return None if value is None else "<run-id>"
    if key == "apply_attempt_id":
        return None if value is None else "<attempt-id>"
    if isinstance(value, Mapping):
        return {
            nested_key: _semantic_value(
                nested_key,
                nested_value,
                tokens=tokens,
            )
            for nested_key, nested_value in sorted(value.items())
        }
    if isinstance(value, (list, tuple)):
        return [_semantic_value(key, nested, tokens=tokens) for nested in value]
    if isinstance(value, str):
        return _normalized_string(value, tokens)
    return value


def _semantic_projection(current: session.LiveStartSession) -> dict[str, object]:
    recovery = current.apply_recovery
    assert isinstance(recovery, Mapping)
    tokens = _normalization_tokens(current)
    return {
        "phase": current.phase.value,
        "pending": current.pending_transition is not None,
        "recovery": _semantic_value("recovery", recovery, tokens=tokens),
    }


def _offset_action_indices(
    value: object,
    *,
    offset: int,
    field_name: str | None = None,
) -> object:
    if isinstance(value, Mapping):
        return {
            key: _offset_action_indices(
                nested,
                offset=offset,
                field_name=key,
            )
            for key, nested in value.items()
        }
    if isinstance(value, list):
        return [
            _offset_action_indices(item, offset=offset, field_name=field_name)
            for item in value
        ]
    if field_name in {"action_index", "expected_action_index"}:
        if value is None:
            return None
        assert type(value) is int
        return value + offset
    return value


def _semantic_with_action_offset(
    semantic: Mapping[str, object],
    *,
    offset: int,
) -> dict[str, object]:
    adjusted = _offset_action_indices(semantic, offset=offset)
    assert isinstance(adjusted, dict)
    return adjusted


def _is_planned_materialization(semantic: Mapping[str, object]) -> bool:
    recovery = semantic["recovery"]
    assert isinstance(recovery, Mapping)
    external = recovery.get("external_file_action")
    return (
        recovery.get("expected_action") == "materialize_file_action_staging"
        and isinstance(external, Mapping)
        and external.get("stage") == "PLANNED"
    )


def _relative_runtime_path(
    value: object,
    *,
    tokens: tuple[tuple[str, str], ...],
) -> str:
    normalized = _normalized_string(str(value), tokens)
    prefix = "<runtime-root>/"
    assert normalized.startswith(prefix)
    return normalized.removeprefix(prefix)


def _declared_change_roots(current: session.LiveStartSession) -> tuple[str, ...]:
    recovery = current.apply_recovery
    assert isinstance(recovery, Mapping)
    tokens = _normalization_tokens(current)
    action = recovery["expected_action"]
    external = recovery["external_file_action"]
    roots: set[str] = set()
    if isinstance(external, Mapping):
        if action == "materialize_file_action_staging":
            roots.add(_relative_runtime_path(external["staging_path"], tokens=tokens))
        else:
            roots.add(_relative_runtime_path(external["final_path"], tokens=tokens))
            roots.add(_relative_runtime_path(external["staging_path"], tokens=tokens))
    if action in {"bind_created_candidate", "materialize_candidate_tree_entry"}:
        roots.add(_relative_runtime_path(recovery["candidate_path"], tokens=tokens))
    if action == "rename_candidate_to_target":
        roots.add(_relative_runtime_path(recovery["candidate_path"], tokens=tokens))
        roots.add(
            _relative_runtime_path(recovery["renamed_target_path"], tokens=tokens)
        )
    return tuple(sorted(roots))


def _normalized_tree_paths(
    current: session.LiveStartSession,
    tree: Mapping[str, object],
) -> dict[str, object]:
    tokens = _normalization_tokens(current)
    return {_normalized_string(path, tokens): value for path, value in tree.items()}


def _snapshot(current: session.LiveStartSession) -> dict[str, object]:
    layout = current.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    runtime_root = Path(str(layout["runtime_root"]))
    lock_path = runtime_root / ".hsconfig/apply.lock"
    tree = _runtime_tree(runtime_root, held_lock_path=lock_path)
    return {
        "session": current.to_value(),
        "semantic": _semantic_projection(current),
        "tree": tree,
        "normalized_tree": _normalized_tree_paths(current, tree),
        "declared_change_roots": _declared_change_roots(current),
    }


def _load_worker_session(session_root: Path) -> session.LiveStartSession:
    session_path = session_root / "session.json"
    return session._load_session_bytes(
        session_path.read_bytes(),
        session_identity=path_identity(session_path),
    )


def _baseline_worker(session_root_text: str, oracle_path_text: str) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    events: list[dict[str, object]] = []
    counts, previous_profile = _start_apply_entry_observer()

    def trace(point: LiveStartFaultPoint) -> None:
        if point not in {_PRE_CAS, _POST_CAS}:
            return
        events.append(
            {
                "boundary": "pre" if point is _PRE_CAS else "post",
                **_snapshot(_load_worker_session(session_root)),
            }
        )

    try:
        result = controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=trace,
        )
        terminal = session.load_live_start_session(
            session_root,
            local_app_data_root=session_root.parents[2],
        )
    finally:
        sys.setprofile(previous_profile)
    _persist_worker_oracle(
        Path(oracle_path_text),
        {
            "status": result.status,
            "counts": counts,
            "events": events,
            "terminal_sha256": terminal.content_sha256,
        },
    )


def _chain_kill_worker(
    session_root_text: str,
    oracle_path_text: str,
    boundary: str,
    expected_pre_text: str,
    expected_post_text: str,
    expected_retirement_text: str | None,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    expected_pre = json.loads(expected_pre_text)
    expected_post = json.loads(expected_post_text)
    expected_retirement = (
        None
        if expected_retirement_text is None
        else json.loads(expected_retirement_text)
    )
    counts, previous_profile = _start_apply_entry_observer()
    repeated_pre: dict[str, object] | None = None
    retirement_pre: dict[str, object] | None = None
    retirement_post: dict[str, object] | None = None
    materialize_pre: dict[str, object] | None = None
    physical_actions: list[str] = []
    real_recover = controller._published_apply.recover_runtime_attempt_from_pair

    def traced_recover(*args: object, **kwargs: object) -> object:
        authorization = kwargs.get("nonterminal_recovery_authorization")
        bearer = getattr(authorization, "_opaque", None)
        action = getattr(bearer, "action", None)
        result = real_recover(*args, **kwargs)
        if action is not None:
            assert isinstance(action, str)
            physical_actions.append(action)
        return result

    controller._published_apply.recover_runtime_attempt_from_pair = traced_recover

    def hard_kill(point: LiveStartFaultPoint) -> None:
        nonlocal repeated_pre, retirement_pre, retirement_post, materialize_pre
        if point is _PRE_CAS:
            observed = _snapshot(_load_worker_session(session_root))
            if boundary == "pre":
                assert observed["semantic"] == expected_pre
                recovery = expected_pre["recovery"]
                assert isinstance(recovery, Mapping)
                assert physical_actions == [recovery["expected_action"]]
                _persist_worker_oracle(
                    Path(oracle_path_text),
                    {
                        "boundary": "pre",
                        "counts": counts,
                        "physical_actions": physical_actions,
                        **observed,
                    },
                )
                os._exit(_HARD_EXIT)
            assert boundary == "post"
            if expected_retirement is None:
                assert observed["semantic"] == expected_pre
                assert repeated_pre is None
                repeated_pre = observed
                return
            if retirement_pre is None:
                assert observed["semantic"] == expected_pre
                assert physical_actions == ["retire_unbound_file_action_staging"]
                retirement_pre = observed
                return
            assert retirement_post is not None
            assert materialize_pre is None
            assert observed["semantic"] == expected_retirement
            assert physical_actions == [
                "retire_unbound_file_action_staging",
                "materialize_file_action_staging",
            ]
            materialize_pre = observed
            return
        if point is _POST_CAS:
            assert boundary == "post"
            observed = _snapshot(_load_worker_session(session_root))
            if expected_retirement is not None and retirement_post is None:
                assert retirement_pre is not None
                assert observed["semantic"] == expected_retirement
                assert physical_actions == ["retire_unbound_file_action_staging"]
                retirement_post = observed
                return
            if expected_retirement is not None:
                assert retirement_pre is not None
                assert retirement_post is not None
                assert materialize_pre is not None
                assert observed["semantic"] == expected_post
                assert physical_actions == [
                    "retire_unbound_file_action_staging",
                    "materialize_file_action_staging",
                ]
                _persist_worker_oracle(
                    Path(oracle_path_text),
                    {
                        "boundary": "post",
                        "counts": counts,
                        "physical_actions": physical_actions,
                        "retirement_pre": retirement_pre,
                        "retirement_post": retirement_post,
                        "materialize_pre": materialize_pre,
                        "post": observed,
                    },
                )
                os._exit(_HARD_EXIT)
            assert repeated_pre is not None
            assert observed["semantic"] == expected_post
            _persist_worker_oracle(
                Path(oracle_path_text),
                {
                    "boundary": "post",
                    "counts": counts,
                    "physical_actions": physical_actions,
                    "repeated_pre": repeated_pre,
                    "post": observed,
                },
            )
            os._exit(_HARD_EXIT)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=hard_kill,
        )
    finally:
        controller._published_apply.recover_runtime_attempt_from_pair = real_recover
        sys.setprofile(previous_profile)
    os._exit(_HARD_EXIT + 1)


def _assert_tree_after_exit(
    *,
    runtime_root: Path,
    snapshot: Mapping[str, object],
) -> None:
    recorded = snapshot["tree"]
    assert isinstance(recorded, Mapping)
    lock_row = recorded[".hsconfig/apply.lock"]
    assert isinstance(lock_row, Mapping)
    assert lock_row == {
        "kind": "file",
        "identity": lock_row["identity"],
        "size": 0,
        "sha256": None,
    }
    lock_fingerprint = _file_fingerprint(runtime_root / ".hsconfig/apply.lock")
    assert lock_fingerprint == (
        tuple(lock_row["identity"]),
        0,
        _sha256_bytes(b""),
    )
    observed = _runtime_tree(runtime_root, held_lock_path=None)
    observed[".hsconfig/apply.lock"]["sha256"] = None
    assert observed == recorded


def _chain_authority(
    *,
    fixture: Any,
    prepared: Any,
    current: session.LiveStartSession,
) -> _ChainAuthority:
    value = current.to_value()
    recovery = value["apply_recovery"]
    layout = value["runtime_layout_bootstrap"]
    admission = value["runtime_admission_binding"]
    operation = value["output_operation_admission_binding"]
    child = value["output_child_binding"]
    publication = value["publication_binding"]
    for mapping in (recovery, layout, admission, operation, child, publication):
        assert isinstance(mapping, dict)
    attempt_id = str(recovery["apply_attempt_id"])
    assert layout["apply_attempt_id"] == attempt_id
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == current.apply_invocation_sha256
    invocation_fingerprint = _file_fingerprint(invocation_path)
    admission_path = Path(str(admission["admission_path"]))
    admission_fingerprint = _file_fingerprint(admission_path)
    profile_fingerprint = _file_fingerprint(operator_profile_path())
    assert invocation_fingerprint is not None
    assert admission_fingerprint is not None
    assert profile_fingerprint is not None
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    return _ChainAuthority(
        frozen_identity=_frozen_identity(current),
        profile_fingerprint=profile_fingerprint,
        output_root=output_root,
        publication_tree=_physical_tree(output_root),
        attempt_id=attempt_id,
        apply_invocation_sha256=str(current.apply_invocation_sha256),
        apply_invocation_fingerprint=invocation_fingerprint,
        runtime_admission_binding=admission,
        runtime_admission_fingerprint=admission_fingerprint,
        runtime_layout_bootstrap=layout,
        output_operation_admission_binding=operation,
        output_child_binding=child,
        publication_binding=publication,
    )


def _assert_chain_authority(
    *,
    prepared: Any,
    current: session.LiveStartSession,
    authority: _ChainAuthority,
) -> None:
    value = current.to_value()
    recovery = value["apply_recovery"]
    assert isinstance(recovery, dict)
    assert current.phase.value == "APPLY_STARTED"
    assert current.pending_transition is None
    assert recovery["recovery_stage"] == "ACTIVE"
    assert recovery["install_route"] == "new_target"
    assert recovery["apply_attempt_id"] == authority.attempt_id
    assert _frozen_identity(current) == authority.frozen_identity
    assert current.apply_invocation_sha256 == authority.apply_invocation_sha256
    assert value["runtime_admission_binding"] == authority.runtime_admission_binding
    assert value["runtime_layout_bootstrap"] == authority.runtime_layout_bootstrap
    assert (
        value["output_operation_admission_binding"]
        == authority.output_operation_admission_binding
    )
    assert value["output_child_binding"] == authority.output_child_binding
    assert value["publication_binding"] == authority.publication_binding
    assert _file_fingerprint(operator_profile_path()) == (authority.profile_fingerprint)
    assert _physical_tree(authority.output_root) == authority.publication_tree
    assert (
        _file_fingerprint(prepared.run_root / "receipts/apply_invocation.json")
        == authority.apply_invocation_fingerprint
    )
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        prepared.run_root / "receipts/apply_invocation.json",
    )
    admission_path = Path(str(authority.runtime_admission_binding["admission_path"]))
    assert _file_fingerprint(admission_path) == authority.runtime_admission_fingerprint
    physical_admission = load_runtime_live_attempt_admission()
    assert physical_admission is not None
    assert physical_admission.apply_attempt_id == authority.attempt_id
    _assert_intermediate_transaction_inventory(
        current=current,
        attempt_id=authority.attempt_id,
    )


def _assert_intermediate_transaction_inventory(
    *,
    current: session.LiveStartSession,
    attempt_id: str,
) -> None:
    recovery = current.apply_recovery
    layout = current.runtime_layout_bootstrap
    assert isinstance(recovery, Mapping)
    assert isinstance(layout, Mapping)
    runtime_root = Path(str(recovery["runtime_root"]))
    transactions = runtime_root / ".hsconfig/transactions"
    transaction_row = layout["directories"][
        session.RUNTIME_LAYOUT_DIRECTORY_ROLES.index("transactions")
    ]
    assert transaction_row["path"] == str(transactions)
    transactions_status = transactions.lstat()
    assert stat.S_ISDIR(transactions_status.st_mode)
    assert not status_is_reparse(transactions_status)
    assert path_identity(transactions) == tuple(transaction_row["successor_identity"])

    expected_final = runtime_transaction_journal_path(runtime_root, attempt_id)
    external = recovery.get("external_file_action")
    external_paths: set[Path] = set()
    if isinstance(external, Mapping):
        for field_name in ("staging_path", "inner_temp_path"):
            path = Path(str(external[field_name]))
            if path.parent == transactions:
                assert path_identity(path.parent) == tuple(external["parent_identity"])
                external_paths.add(path)

    allowed = {path for path in external_paths if os.path.lexists(path)}
    final_status = expected_final.lstat() if os.path.lexists(expected_final) else None
    if final_status is not None:
        allowed.add(expected_final)
    observed: set[Path] = set()
    with os.scandir(transactions) as iterator:
        for entry in iterator:
            path = Path(entry.path)
            status = path.lstat()
            assert stat.S_ISREG(status.st_mode)
            assert not status_is_reparse(status)
            assert status.st_nlink == 1
            assert path.parent == transactions
            assert path_identity(path.parent) == tuple(
                transaction_row["successor_identity"]
            )
            assert path in allowed
            observed.add(path)
    assert observed == allowed

    if isinstance(external, Mapping):
        staging_path = Path(str(external["staging_path"]))
        inner_path = Path(str(external["inner_temp_path"]))
        if staging_path in observed:
            staging_fingerprint = _file_fingerprint(staging_path)
            assert staging_fingerprint is not None
            if external["stage"] == "STAGING_BOUND":
                assert staging_fingerprint == (
                    tuple(external["staging_identity"]),
                    external["staging_size"],
                    external["staging_sha256"],
                )
            else:
                assert external["stage"] == "PLANNED"
                assert staging_fingerprint[1:] == (
                    external["planned_successor_size"],
                    external["planned_successor_sha256"],
                )
        if inner_path in observed:
            inner_status = inner_path.lstat()
            assert external["stage"] == "PLANNED"
            assert inner_status.st_size <= external["planned_successor_size"]

    if final_status is None:
        assert expected_final not in observed
        for prefix in ("predecessor", "successor"):
            assert not (
                recovery.get(f"{prefix}_journal_path") == str(expected_final)
                and (
                    recovery.get(f"{prefix}_journal_identity") is not None
                    or recovery.get(f"{prefix}_journal_sha256") is not None
                )
            )
        if isinstance(external, Mapping) and external.get("final_path") == str(
            expected_final
        ):
            assert external.get("predecessor_state") == "absent"
            if external.get("stage") == "STAGING_BOUND":
                assert Path(str(external["staging_path"])) in observed
        return
    assert stat.S_ISREG(final_status.st_mode)
    assert final_status.st_nlink == 1
    journal = read_runtime_transaction_journal(expected_final)
    assert journal.transaction_id == attempt_id
    fingerprint = _file_fingerprint(expected_final)
    assert fingerprint is not None

    expected_triplet: tuple[tuple[int, int, int], int | None, str] | None = None
    if isinstance(external, Mapping) and external.get("final_path") == str(
        expected_final
    ):
        staging_path = Path(str(external["staging_path"]))
        if external.get("stage") == "STAGING_BOUND" and staging_path not in observed:
            expected_triplet = (
                tuple(external["staging_identity"]),
                int(external["staging_size"]),
                str(external["staging_sha256"]),
            )
        elif external.get("predecessor_state") == "exact":
            expected_triplet = (
                tuple(external["predecessor_identity"]),
                int(external["predecessor_size"]),
                str(external["predecessor_sha256"]),
            )
    if expected_triplet is None and recovery.get("successor_journal_path") == str(
        expected_final
    ):
        identity = recovery.get("successor_journal_identity")
        digest = recovery.get("successor_journal_sha256")
        if identity is not None and digest is not None:
            expected_triplet = (tuple(identity), None, str(digest))
    if expected_triplet is None and recovery.get("predecessor_journal_path") == str(
        expected_final
    ):
        identity = recovery.get("predecessor_journal_identity")
        digest = recovery.get("predecessor_journal_sha256")
        if identity is not None and digest is not None:
            expected_triplet = (tuple(identity), None, str(digest))
    assert expected_triplet is not None
    expected_identity, expected_size, expected_sha256 = expected_triplet
    assert fingerprint[0] == expected_identity
    if expected_size is not None:
        assert fingerprint[1] == expected_size
    assert fingerprint[2] == expected_sha256


def _changed_paths(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> set[str]:
    return {
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    }


def _path_declared(path: str, roots: set[str]) -> bool:
    return any(path == root or path.startswith(root + "/") for root in roots)


def _assert_initial_pre_tree(
    current: session.LiveStartSession,
    snapshot: Mapping[str, object],
) -> None:
    recovery = current.apply_recovery
    layout = current.runtime_layout_bootstrap
    assert isinstance(recovery, Mapping)
    assert isinstance(layout, Mapping)
    assert recovery["expected_action"] == "materialize_file_action_staging"
    external = recovery["external_file_action"]
    assert isinstance(external, Mapping)
    assert external["stage"] == "PLANNED"
    assert external["commit_mode"] == "create_no_replace"
    tokens = _normalization_tokens(current)
    expected_paths = {".", ".hsconfig", ".hsconfig/apply.lock"}
    expected_paths.update(
        _relative_runtime_path(row["path"], tokens=tokens)
        for row in layout["directories"]
    )
    expected_paths.update(_declared_change_roots(current))
    normalized_tree = snapshot["normalized_tree"]
    assert isinstance(normalized_tree, Mapping)
    assert set(normalized_tree) == expected_paths


def _planned_residue_paths(
    current: session.LiveStartSession,
) -> tuple[str, str, Mapping[str, object]]:
    recovery = current.apply_recovery
    assert isinstance(recovery, Mapping)
    assert recovery["expected_action"] == "materialize_file_action_staging"
    external = recovery["external_file_action"]
    assert isinstance(external, Mapping)
    assert external["stage"] == "PLANNED"
    tokens = _normalization_tokens(current)
    return (
        _relative_runtime_path(external["staging_path"], tokens=tokens),
        _relative_runtime_path(external["inner_temp_path"], tokens=tokens),
        external,
    )


def _assert_planned_materialization(
    *,
    current: session.LiveStartSession,
    snapshot: Mapping[str, object],
) -> tuple[str, str]:
    staging_path, inner_path, external = _planned_residue_paths(current)
    tree = snapshot["normalized_tree"]
    assert isinstance(tree, Mapping)
    assert inner_path not in tree
    staging = tree[staging_path]
    assert isinstance(staging, Mapping)
    assert staging == {
        "kind": "file",
        "identity": staging["identity"],
        "size": external["planned_successor_size"],
        "sha256": external["planned_successor_sha256"],
    }
    return staging_path, inner_path


def _baseline_pairs(
    events: list[dict[str, object]],
) -> list[tuple[dict[str, object], dict[str, object]]]:
    assert len(events) >= 2
    assert len(events) % 2 == 0
    pairs: list[tuple[dict[str, object], dict[str, object]]] = []
    for index in range(0, len(events), 2):
        pre = events[index]
        post = events[index + 1]
        assert pre["boundary"] == "pre"
        assert post["boundary"] == "post"
        assert pre["tree"] == post["tree"]
        pairs.append((pre, post))
    return pairs


def _assert_baseline_coverage(
    pairs: list[tuple[dict[str, object], dict[str, object]]],
) -> None:
    actions = [
        str(pre["session"]["apply_recovery"]["expected_action"]) for pre, _post in pairs
    ]
    required = {
        "bind_candidate_fence",
        "materialize_file_action_staging",
        "commit_bound_initial_attempt_record",
        "advance_controller_transaction_journal_write",
        "bind_created_candidate",
        "commit_bound_candidate_planned_attempt_record",
        "materialize_candidate_tree_entry",
        "verify_candidate_tree",
        "rename_candidate_to_target",
        "bind_renamed_target",
        "write_deck_config_ini",
        "commit_ini_journal",
        "write_runtime_state",
        "commit_state_journal",
        "write_last_apply_receipt",
        "finalize_journal",
        "finalize_attempt_record",
        "observe_committed",
    }
    assert required <= set(actions)
    external_stages = {
        pre["session"]["apply_recovery"]["external_file_action"]["stage"]
        for pre, _post in pairs
        if isinstance(
            pre["session"]["apply_recovery"]["external_file_action"],
            dict,
        )
    }
    assert {"PLANNED", "STAGING_BOUND"} <= external_stages


def test_real_new_target_runtime_action_chain_hard_kills_before_and_after_each_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_state = tmp_path / "baseline-state"
    baseline_state.mkdir()
    _local_state(baseline_state, monkeypatch)
    baseline_fixture, baseline_prepared = _prepare_approved(
        tmp_path / "baseline-work",
        monkeypatch,
    )
    baseline_oracle_path = tmp_path / "baseline-oracle.json"
    _spawn_and_join(
        target=_baseline_worker,
        args=(str(baseline_prepared.run_root), str(baseline_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    baseline_oracle = json.loads(baseline_oracle_path.read_bytes())
    assert baseline_oracle["status"] == "LIVE_AND_MATCHED"
    assert baseline_oracle["counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    baseline_terminal = session.load_live_start_session(
        baseline_prepared.run_root,
        local_app_data_root=baseline_prepared.run_root.parents[2],
    )
    assert baseline_terminal.content_sha256 == baseline_oracle["terminal_sha256"]
    _matched_package(baseline_fixture)
    pairs = _baseline_pairs(baseline_oracle["events"])
    _assert_baseline_coverage(pairs)
    baseline_lock = _file_fingerprint(
        baseline_fixture.profile.runtime_root / ".hsconfig/apply.lock"
    )
    assert baseline_lock is not None
    for pre, post in pairs:
        for snapshot in (pre, post):
            lock_row = snapshot["tree"][".hsconfig/apply.lock"]
            assert tuple(lock_row["identity"]) == baseline_lock[0]
            assert lock_row["size"] == baseline_lock[1] == 0
            assert lock_row["sha256"] is None
    assert baseline_lock[2] == _sha256_bytes(b"")

    chain_state = tmp_path / "chain-state"
    chain_state.mkdir()
    _local_state(chain_state, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "chain-work", monkeypatch)
    runtime_root = fixture.profile.runtime_root
    markers = tmp_path / "chain-markers"
    markers.mkdir()
    authority: _ChainAuthority | None = None
    previous_post: dict[str, object] | None = None
    previous_post_session: session.LiveStartSession | None = None
    baseline_post_previous: dict[str, object] | None = None
    action_index_offset = 0
    planned_retirement_count = 0

    for ordinal, (baseline_pre, baseline_post) in enumerate(pairs):
        baseline_pre_semantic = baseline_pre["semantic"]
        baseline_post_semantic = baseline_post["semantic"]
        assert isinstance(baseline_pre_semantic, Mapping)
        assert isinstance(baseline_post_semantic, Mapping)
        planned_recovery = _is_planned_materialization(baseline_pre_semantic)
        expected_pre = _semantic_with_action_offset(
            baseline_pre_semantic,
            offset=action_index_offset,
        )
        expected_retirement = (
            _semantic_with_action_offset(
                baseline_pre_semantic,
                offset=action_index_offset + 1,
            )
            if planned_recovery
            else None
        )
        expected_post = _semantic_with_action_offset(
            baseline_post_semantic,
            offset=action_index_offset + (1 if planned_recovery else 0),
        )
        pre_path = markers / f"{ordinal:03d}-pre.json"
        _spawn_and_join(
            target=_chain_kill_worker,
            args=(
                str(prepared.run_root),
                str(pre_path),
                "pre",
                json.dumps(expected_pre, sort_keys=True, separators=(",", ":")),
                json.dumps(expected_post, sort_keys=True, separators=(",", ":")),
                None,
            ),
            expected_exitcode=_HARD_EXIT,
            timeout_seconds=360,
        )
        pre = json.loads(pre_path.read_bytes())
        assert pre.pop("boundary") == "pre"
        pre_counts = pre.pop("counts")
        expected_action = expected_pre["recovery"]["expected_action"]
        assert pre.pop("physical_actions") == [expected_action]
        assert pre_counts == (
            _expected_apply_entry_counts(
                fresh=1,
                install_prepare=1,
                attempt_prepare=1,
            )
            if ordinal == 0
            else _expected_apply_entry_counts(recovery=1)
        )
        current = session.load_live_start_session(
            prepared.run_root,
            local_app_data_root=prepared.run_root.parents[2],
        )
        pre_current = current
        assert pre["session"] == current.to_value()
        assert pre["semantic"] == expected_pre
        _assert_tree_after_exit(runtime_root=runtime_root, snapshot=pre)
        if authority is None:
            authority = _chain_authority(
                fixture=fixture,
                prepared=prepared,
                current=current,
            )
            assert current.apply_recovery["recovery_stage"] == "ACTIVE"
            assert current.apply_recovery["install_route"] == "new_target"
            _assert_initial_pre_tree(current, pre)
        _assert_chain_authority(
            prepared=prepared,
            current=current,
            authority=authority,
        )

        if previous_post is not None:
            assert previous_post_session is not None
            assert baseline_post_previous is not None
            expected_changed = _changed_paths(
                baseline_post_previous["normalized_tree"],
                baseline_pre["normalized_tree"],
            )
            changed = _changed_paths(
                previous_post["normalized_tree"],
                pre["normalized_tree"],
            )
            assert changed == expected_changed
            declared_roots = set(previous_post["declared_change_roots"])
            assert declared_roots == set(_declared_change_roots(previous_post_session))
            assert all(_path_declared(path, declared_roots) for path in changed)

        post_path = markers / f"{ordinal:03d}-post.json"
        _spawn_and_join(
            target=_chain_kill_worker,
            args=(
                str(prepared.run_root),
                str(post_path),
                "post",
                json.dumps(expected_pre, sort_keys=True, separators=(",", ":")),
                json.dumps(expected_post, sort_keys=True, separators=(",", ":")),
                (
                    json.dumps(
                        expected_retirement,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if expected_retirement is not None
                    else None
                ),
            ),
            expected_exitcode=_HARD_EXIT,
            timeout_seconds=360,
        )
        post_oracle = json.loads(post_path.read_bytes())
        assert post_oracle.pop("boundary") == "post"
        assert post_oracle.pop("counts") == _expected_apply_entry_counts(recovery=1)
        post = post_oracle["post"]
        if planned_recovery:
            assert post_oracle.pop("physical_actions") == [
                "retire_unbound_file_action_staging",
                "materialize_file_action_staging",
            ]
            retirement_pre = post_oracle["retirement_pre"]
            retirement_post = post_oracle["retirement_post"]
            materialize_pre = post_oracle["materialize_pre"]
            assert retirement_pre["session"] == pre["session"]
            assert retirement_pre["semantic"] == expected_pre
            assert (
                retirement_pre["declared_change_roots"] == pre["declared_change_roots"]
            )
            assert retirement_post["semantic"] == expected_retirement
            assert retirement_post["tree"] == retirement_pre["tree"]
            assert (
                retirement_post["normalized_tree"] == retirement_pre["normalized_tree"]
            )
            assert materialize_pre["session"] == retirement_post["session"]
            assert materialize_pre["semantic"] == expected_retirement
            assert (
                materialize_pre["declared_change_roots"]
                == retirement_post["declared_change_roots"]
            )
            pre_recovery = pre["session"]["apply_recovery"]
            retired_recovery = retirement_post["session"]["apply_recovery"]
            assert retired_recovery["expected_action"] == (
                "materialize_file_action_staging"
            )
            assert retired_recovery["action_index"] == (
                pre_recovery["action_index"] + 1
            )
            assert retired_recovery["external_file_action"]["stage"] == "PLANNED"
            assert retired_recovery["external_file_action"]["action_index"] == (
                pre_recovery["external_file_action"]["action_index"] + 1
            )
            staging_path, inner_path = _assert_planned_materialization(
                current=pre_current,
                snapshot=pre,
            )
            retired_tree = retirement_pre["normalized_tree"]
            assert isinstance(retired_tree, dict)
            assert staging_path not in retired_tree
            assert inner_path not in retired_tree
            assert _changed_paths(pre["normalized_tree"], retired_tree) == {
                staging_path
            }
            fresh_staging_path, fresh_inner_path = _assert_planned_materialization(
                current=pre_current,
                snapshot=materialize_pre,
            )
            assert (fresh_staging_path, fresh_inner_path) == (
                staging_path,
                inner_path,
            )
            assert _changed_paths(
                retirement_post["normalized_tree"],
                materialize_pre["normalized_tree"],
            ) == {staging_path}
            assert post["tree"] == materialize_pre["tree"]
        else:
            assert post_oracle.pop("physical_actions") == [expected_action]
            repeated_pre = post_oracle["repeated_pre"]
            assert repeated_pre["session"] == pre["session"]
            assert repeated_pre["semantic"] == pre["semantic"]
            assert repeated_pre["tree"] == pre["tree"]
            assert repeated_pre["normalized_tree"] == pre["normalized_tree"]
            assert repeated_pre["declared_change_roots"] == pre["declared_change_roots"]
            assert post["tree"] == repeated_pre["tree"]
        assert post["semantic"] == expected_post
        current = session.load_live_start_session(
            prepared.run_root,
            local_app_data_root=prepared.run_root.parents[2],
        )
        assert post["session"] == current.to_value()
        _assert_tree_after_exit(runtime_root=runtime_root, snapshot=post)
        _assert_chain_authority(
            prepared=prepared,
            current=current,
            authority=authority,
        )
        if planned_recovery:
            post_recovery = current.apply_recovery
            assert isinstance(post_recovery, Mapping)
            post_external = post_recovery["external_file_action"]
            assert isinstance(post_external, Mapping)
            staging_row = post["normalized_tree"][staging_path]
            assert isinstance(staging_row, Mapping)
            assert tuple(staging_row["identity"]) == tuple(
                post_external["staging_identity"]
            )
            assert staging_row["size"] == post_external["staging_size"]
            assert staging_row["sha256"] == post_external["staging_sha256"]
            assert post_recovery["action_index"] == (
                pre_current.apply_recovery["action_index"] + 2
            )
            planned_retirement_count += 1
            action_index_offset += 1
        previous_post = post
        previous_post_session = current
        baseline_post_previous = baseline_post

    assert authority is not None
    assert planned_retirement_count == sum(
        _is_planned_materialization(pre["semantic"]) for pre, _post in pairs
    )
    assert action_index_offset == planned_retirement_count
    resume_oracle_path = markers / "final-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resume_oracle = json.loads(resume_oracle_path.read_bytes())
    assert resume_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts(
        recovery=1
    )
    assert resume_oracle["status"] == "LIVE_AND_MATCHED"
    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert terminal.content_sha256 == resume_oracle["session_sha256"]
    assert _frozen_identity(terminal) == authority.frozen_identity
    assert terminal.apply_invocation_sha256 == authority.apply_invocation_sha256
    terminal_value = terminal.to_value()
    assert (
        terminal_value["runtime_admission_binding"]
        == authority.runtime_admission_binding
    )
    assert (
        terminal_value["runtime_layout_bootstrap"] == authority.runtime_layout_bootstrap
    )
    assert terminal_value["publication_binding"] == authority.publication_binding
    assert terminal.result_intent["apply_attempt_id"] == authority.attempt_id
    assert terminal.terminal_retirement["apply_attempt_id"] == authority.attempt_id
    assert terminal.attempt_acknowledgement["apply_attempt_id"] == authority.attempt_id
    invocation = load_apply_invocation(
        prepared.run_root / "receipts/apply_invocation.json"
    )
    assert invocation.apply_attempt_id == authority.attempt_id
    assert invocation.content_sha256 == terminal.apply_invocation_sha256
    assert _file_fingerprint(operator_profile_path()) == authority.profile_fingerprint
    assert _physical_tree(authority.output_root) == authority.publication_tree
    assert (
        _file_fingerprint(prepared.run_root / "receipts/apply_invocation.json")
        == authority.apply_invocation_fingerprint
    )
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        prepared.run_root / "receipts/apply_invocation.json",
    )
    _output, _package, runtime_target = _matched_package(fixture)
    journals = load_runtime_transaction_journals(runtime_root)
    assert len(journals) == 1
    assert journals[0].transaction_id == authority.attempt_id
    assert journals[0].owns_target is True
    assert runtime_root / journals[0].target_path == runtime_target
    assert tuple(
        path for path in (runtime_root / "CustomConfig").iterdir() if path.is_dir()
    ) == (runtime_target,)
    assert load_runtime_live_attempt_admission() is None
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())
    assert not tuple((runtime_root / ".hsconfig/attempt-retention").iterdir())

    terminal_bytes = {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "summary_json": (prepared.run_root / "result/summary.json").read_bytes(),
        "summary_markdown": (prepared.run_root / "result/summary.md").read_bytes(),
        "runtime": _physical_tree(runtime_root),
        "publication": _physical_tree(authority.output_root),
    }
    replay_path = markers / "terminal-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay = json.loads(replay_path.read_bytes())
    assert replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay == resume_oracle
    assert (prepared.run_root / "session.json").read_bytes() == terminal_bytes[
        "session"
    ]
    assert (prepared.run_root / "result/summary.json").read_bytes() == (
        terminal_bytes["summary_json"]
    )
    assert (prepared.run_root / "result/summary.md").read_bytes() == (
        terminal_bytes["summary_markdown"]
    )
    assert _physical_tree(runtime_root) == terminal_bytes["runtime"]
    assert _physical_tree(authority.output_root) == terminal_bytes["publication"]
