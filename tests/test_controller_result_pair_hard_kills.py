from __future__ import annotations

from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import stat

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _join_hard_kill_process,
    _persist_worker_oracle,
    _physical_tree,
)


_SELECTED_HARD_EXIT = 93


def _result_pair_hard_exit_worker(
    session_root: str, local_app_data: str, fault_value: str, marker_path: str,
) -> None:
    os.environ["LOCALAPPDATA"] = local_app_data
    selected = LiveStartFaultPoint(fault_value)
    temp_creations: list[str] = []

    def hard_exit(point: LiveStartFaultPoint) -> None:
        if point is LiveStartFaultPoint.AFTER_RESULT_JSON_TEMP_CREATED:
            temp_creations.append("json")
        elif point is LiveStartFaultPoint.AFTER_RESULT_MARKDOWN_TEMP_CREATED:
            temp_creations.append("markdown")
        if point is selected:
            _persist_worker_oracle(
                Path(marker_path),
                {"selected": point.value, "temp_creations": temp_creations},
            )
            os._exit(_SELECTED_HARD_EXIT)

    controller._finalize_live_start(
        session_root=Path(session_root), resume_intake=True, fault_hook=hard_exit,
    )
    # A checkpoint skipped by normal completion must never count as a kill.
    os._exit(_SELECTED_HARD_EXIT + 1)


class ResultIntentStop(BaseException):
    pass


def test_result_pair_hard_kill_matrix_reaches_one_byte_exact_terminal_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Abrupt spawned-process exit chain, not independent fresh permutations.

    Initial result-intent binding uses an exception in the parent; this does
    not prove a hard kill immediately after that CAS. Every listed result-file
    and terminal-CAS checkpoint below terminates a real spawned process.
    """
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)

    def stop_after_intent(point: LiveStartFaultPoint) -> None:
        if point is LiveStartFaultPoint.AFTER_RESULT_INTENT:
            raise ResultIntentStop(point.value)

    with pytest.raises(ResultIntentStop, match="^after_result_intent$"):
        controller._finalize_live_start(
            session_root=prepared.run_root, fault_hook=stop_after_intent,
        )
    initial = session.load_live_start_session(prepared.run_root)
    intent = initial.result_intent
    assert intent is not None
    assert intent["terminal_status"] == "LIVE_AND_MATCHED"
    assert intent["physical_disposition"] == "COMMITTED"
    assert initial.terminal_status is None
    assert initial.apply_recovery is None
    assert initial.closed_apply_recovery_commitment["recovery_stage"] == "CLOSED"
    expected_json, expected_markdown = session._live_start_result_payloads(intent)
    expected_pair = {"summary.json": expected_json, "summary.md": expected_markdown}
    result_root = prepared.run_root / "result"
    assert not result_root.exists()
    root_identity = path_identity(prepared.run_root)
    frozen_before = _physical_tree(prepared.run_root / "inputs")
    runtime_root = fixture.profile.runtime_root
    runtime_before = _physical_tree(runtime_root)
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == intent["apply_attempt_id"]
    admission_before = (path_identity(admission.admission_path), admission.admission_path.read_bytes())
    journals = load_runtime_transaction_journals(runtime_root)
    assert len(journals) == 1
    owner = journals[0]
    assert owner.transaction_id == admission.apply_attempt_id
    assert owner.phase is RuntimeTransactionPhase.FINALIZED
    assert owner.owns_target is True
    owner_path = runtime_transaction_journal_path(runtime_root, owner.transaction_id)
    owner_before = (path_identity(owner_path), owner_path.read_bytes())
    assert admission.retention_fence_path.is_file()

    points = (
        LiveStartFaultPoint.AFTER_RESULT_JSON_TEMP_CREATED,
        LiveStartFaultPoint.AFTER_RESULT_JSON_TEMP_PARTIAL,
        LiveStartFaultPoint.AFTER_RESULT_JSON_TEMP_FULL,
        LiveStartFaultPoint.AFTER_RESULT_JSON_TEMP_FLUSHED,
        LiveStartFaultPoint.BEFORE_RESULT_JSON_REPLACE,
        LiveStartFaultPoint.AFTER_RESULT_JSON,
        LiveStartFaultPoint.AFTER_RESULT_MARKDOWN_TEMP_CREATED,
        LiveStartFaultPoint.AFTER_RESULT_MARKDOWN_TEMP_PARTIAL,
        LiveStartFaultPoint.AFTER_RESULT_MARKDOWN_TEMP_FULL,
        LiveStartFaultPoint.AFTER_RESULT_MARKDOWN_TEMP_FLUSHED,
        LiveStartFaultPoint.BEFORE_RESULT_MARKDOWN_REPLACE,
        LiveStartFaultPoint.AFTER_RESULT_MARKDOWN,
        LiveStartFaultPoint.BEFORE_TERMINAL_CAS,
        LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK,
    )
    markers = tmp_path / "hard-exit-markers"
    markers.mkdir()
    context = multiprocessing.get_context("spawn")
    final_identities: dict[str, tuple[int, int, int]] = {}
    result_root_identity = None
    for ordinal, point in enumerate(points):
        marker = markers / f"{ordinal:02d}.json"
        process = context.Process(
            target=_result_pair_hard_exit_worker,
            args=(
                str(prepared.run_root), os.environ["LOCALAPPDATA"], point.value, str(marker),
            ),
        )
        process.start()
        _join_hard_kill_process(process, expected_exitcode=_SELECTED_HARD_EXIT)
        # A fresh TEMP_CREATED event on every retry proves reserved residue was
        # not simply promoted, even when its previous bytes were already full.
        assert json.loads(marker.read_bytes()) == {
            "selected": point.value,
            "temp_creations": ["json"] if ordinal < 6 else ["markdown"] if ordinal < 12 else [],
        }
        persisted = session.load_live_start_session(prepared.run_root)
        assert persisted.result_intent == intent
        assert persisted.closed_apply_recovery_commitment == initial.closed_apply_recovery_commitment
        assert persisted.attempt_acknowledgement == initial.attempt_acknowledgement
        assert persisted.apply_recovery is None
        assert persisted.pending_transition is None
        assert persisted.terminal_retirement is None
        if point is LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK:
            assert persisted.terminal_status == "LIVE_AND_MATCHED"
            for name, payload in expected_pair.items():
                assert persisted.artifact_bindings[f"result/{name}"] == "sha256:" + sha256(payload).hexdigest()
        else:
            assert persisted.canonical_json == initial.canonical_json
            assert persisted.terminal_status is None
        assert path_identity(prepared.run_root) == root_identity
        assert _physical_tree(prepared.run_root / "inputs") == frozen_before
        assert _physical_tree(runtime_root) == runtime_before
        assert load_runtime_transaction_journals(runtime_root) == journals
        assert (path_identity(owner_path), owner_path.read_bytes()) == owner_before
        assert load_runtime_live_attempt_admission() == admission
        assert (path_identity(admission.admission_path), admission.admission_path.read_bytes()) == admission_before
        if result_root_identity is None:
            result_root_identity = path_identity(result_root)
        assert path_identity(result_root) == result_root_identity

        expected_names: set[str] = set()
        for name, payload, final_ordinal in (
            ("summary.json", expected_json, 5), ("summary.md", expected_markdown, 11),
        ):
            final = result_root / name
            if ordinal >= final_ordinal:
                expected_names.add(name)
                assert final.read_bytes() == payload
                final_identities.setdefault(name, path_identity(final))
                assert path_identity(final) == final_identities[name]
            else:
                assert not final.exists()
        if ordinal < 5 or 6 <= ordinal < 11:
            surface_ordinal = ordinal if ordinal < 5 else ordinal - 6
            name = "summary.json" if ordinal < 5 else "summary.md"
            payload = expected_pair[name]
            temp_name = f".{name}.live-start-atomic.tmp"
            expected_names.add(temp_name)
            temp = result_root / temp_name
            status = temp.lstat()
            assert stat.S_ISREG(status.st_mode) and status.st_nlink == 1
            assert temp.read_bytes() == (
                b"" if surface_ordinal == 0 else payload[:len(payload) // 2] if surface_ordinal == 1 else payload
            )
        assert {path.name for path in result_root.iterdir()} == expected_names

    result = controller.resume_live_start(session_root=prepared.run_root)
    terminal = session.load_live_start_session(prepared.run_root)
    assert result.status == terminal.terminal_status == "LIVE_AND_MATCHED"
    assert terminal.result_intent == intent
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.terminal_retirement["apply_attempt_id"] == owner.transaction_id
    assert terminal.terminal_retirement["operation"] == "ack_success"
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert load_runtime_live_attempt_admission() is None
    assert not admission.admission_path.exists()
    assert not admission.retention_fence_path.exists()
    remaining_runtime = dict(runtime_before)
    del remaining_runtime[admission.retention_fence_path.relative_to(runtime_root).as_posix()]
    assert _physical_tree(runtime_root) == remaining_runtime
    assert load_runtime_transaction_journals(runtime_root) == journals
    assert (path_identity(owner_path), owner_path.read_bytes()) == owner_before
    assert {path.name: path.read_bytes() for path in result_root.iterdir()} == expected_pair
    assert {name: path_identity(result_root / name) for name in expected_pair} == final_identities
    terminal_tree = _physical_tree(prepared.run_root)
    runtime_tree = _physical_tree(runtime_root)
    replayed = controller.resume_live_start(session_root=prepared.run_root)
    assert replayed.summary.canonical_json == result.summary.canonical_json
    assert _physical_tree(prepared.run_root) == terminal_tree
    assert _physical_tree(runtime_root) == runtime_tree
    assert load_runtime_live_attempt_admission() is None
