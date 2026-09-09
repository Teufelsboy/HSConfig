from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.package_io import path_identity
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
)
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved


def test_commit_then_runtime_drift_reports_applied_but_not_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    runtime_root = fixture.profile.runtime_root
    changed: list[tuple[Path, bytes, str, bytes]] = []

    def drift_after_commit(point: LiveStartFaultPoint) -> None:
        if point is not LiveStartFaultPoint.AFTER_INSTALLER_RETURN_BEFORE_APPLY_COMMITTED:
            return
        assert not changed
        journals = load_runtime_transaction_journals(runtime_root)
        assert len(journals) == 1
        journal = journals[0]
        assert journal.phase is RuntimeTransactionPhase.FINALIZED
        assert journal.owns_target is True
        invocation = load_apply_invocation(prepared.run_root / "receipts/apply_invocation.json")
        admission = load_runtime_live_attempt_admission()
        assert admission is not None
        assert journal.transaction_id == invocation.apply_attempt_id == admission.apply_attempt_id
        target = runtime_root / journal.target_path
        assert target.is_relative_to(runtime_root)
        mulligan = target / "Mulligan.json"
        before = mulligan.read_bytes()
        identity = path_identity(mulligan)
        value = json.loads(before)
        assert value["GameCardId"] == "Mulligan"
        assert value["Mulligan"]["values"][0]["value"] == "hold"
        # Change an existing legal action, not the journal, control plane,
        # file identity, or a caller-supplied replacement authority.
        value["Mulligan"]["values"][0]["value"] = "discard"
        drifted = FrozenJsonDocument.from_value(value).canonical_json
        assert drifted != before
        ini = runtime_root / "CustomConfig/deck_config.ini"
        ini_bytes = ini.read_bytes()
        mulligan.write_bytes(drifted)
        assert path_identity(mulligan) == identity
        changed.append((mulligan, drifted, journal.transaction_id, ini_bytes))

    result = controller._finalize_live_start(
        session_root=prepared.run_root, fault_hook=drift_after_commit,
    )
    assert len(changed) == 1
    mulligan, drifted, attempt_id, ini_bytes = changed[0]
    terminal = session.load_live_start_session(prepared.run_root)
    intent = terminal.result_intent
    assert result.status == terminal.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
    assert terminal.phase is session.LiveStartPhase.APPLY_COMMITTED
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.attempt_acknowledgement is None
    assert intent["apply_attempt_id"] == attempt_id
    assert intent["physical_disposition"] == "COMMITTED"
    assert intent["raw_apply_status"] == "applied"
    assert intent["runtime_match_status"] == "mismatch"
    assert isinstance(intent["runtime_match_sha256"], str)
    assert intent["error_code"] == "runtime_mismatch"
    retirement = terminal.terminal_retirement
    assert retirement["operation"] == "release_committed_mismatch"
    assert retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert retirement["apply_attempt_id"] == attempt_id
    assert retirement["result_intent_sha256"] == intent["content_sha256"]
    assert load_runtime_live_attempt_admission() is None
    assert not Path(intent["runtime_admission_path"]).exists()
    assert mulligan.read_bytes() == drifted
    assert (runtime_root / "CustomConfig/deck_config.ini").read_bytes() == ini_bytes
    journals = load_runtime_transaction_journals(runtime_root)
    assert len(journals) == 1
    assert journals[0].transaction_id == attempt_id
    assert journals[0].phase is RuntimeTransactionPhase.FINALIZED
    assert journals[0].owns_target is True

    retained: dict[Path, tuple[object, bytes]] = {}
    for prefix in (
        "retained_attempt_record", "retained_journal", "retained_target_owner_journal",
    ):
        path = Path(intent[f"{prefix}_path"])
        raw = path.read_bytes()
        identity = path_identity(path)
        assert identity == tuple(intent[f"{prefix}_identity"])
        assert "sha256:" + sha256(raw).hexdigest() == intent[f"{prefix}_sha256"]
        retained[path] = (identity, raw)
    assert len(retained) == 2  # The retained attempt fence and its owning journal.
    session_bytes = (prepared.run_root / "session.json").read_bytes()
    result_pair = {
        name: (prepared.run_root / "result" / name).read_bytes()
        for name in ("summary.json", "summary.md")
    }
    resumed = controller.resume_live_start(session_root=prepared.run_root)
    assert resumed.status == "APPLIED_BUT_NOT_VERIFIED"
    assert resumed.summary.canonical_json == result.summary.canonical_json
    assert (prepared.run_root / "session.json").read_bytes() == session_bytes
    assert {
        name: (prepared.run_root / "result" / name).read_bytes() for name in result_pair
    } == result_pair
    assert {path: (path_identity(path), path.read_bytes()) for path in retained} == retained
    assert load_runtime_transaction_journals(runtime_root) == journals
    assert mulligan.read_bytes() == drifted
    assert (runtime_root / "CustomConfig/deck_config.ini").read_bytes() == ini_bytes
    assert load_runtime_live_attempt_admission() is None
