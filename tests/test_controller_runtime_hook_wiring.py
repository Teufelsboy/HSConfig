from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from hsconfig import live_start_controller as controller
from hsconfig.live_start_faults import LiveStartFaultPoint
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved


def test_real_controller_fires_initial_runtime_creation_hooks_at_exact_boundaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "run", monkeypatch)
    expected = (
        LiveStartFaultPoint.AFTER_RUNTIME_JOURNAL_CREATED.value,
        LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE.value,
        LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_CREATE_BEFORE_CANDIDATE_IDENTITY_RECEIPT_CAS.value,
    )
    observed: list[str] = []
    snapshots: dict[str, dict[str, object]] = {}

    def trace(point: object) -> None:
        label = str(point)
        if label not in expected:
            return
        assert label not in snapshots

        persisted = json.loads((prepared.run_root / "session.json").read_bytes())
        assert persisted["phase"] == "APPLY_STARTED"
        assert persisted["pending_transition"] is None
        recovery = persisted["apply_recovery"]
        assert isinstance(recovery, dict)
        assert recovery["recovery_stage"] == "ACTIVE"
        assert recovery["install_route"] == "new_target"
        assert recovery["runtime_match_status"] == "not_run"

        fence_path = Path(str(recovery["successor_attempt_record_path"]))
        fence = json.loads(fence_path.read_bytes())
        assert fence["state"] == "CANDIDATE_PLANNED"
        assert fence["candidate_identity"] is None
        candidate_path = Path(str(recovery["candidate_path"]))

        if label == expected[0]:
            external = recovery["external_file_action"]
            assert isinstance(external, dict)
            assert recovery["expected_action"] == (
                "advance_controller_transaction_journal_write"
            )
            assert external["stage"] == "STAGING_BOUND"
            assert external["action_kind"] == (
                "advance_controller_transaction_journal_write"
            )
            assert external["commit_mode"] == "create_no_replace"
            assert external["final_path"] == recovery["planned_journal_successor_path"]
            assert recovery["planned_journal_successor_phase"] == "PREPARED"
            assert recovery["successor_journal_path"] is None
            assert recovery["successor_journal_identity"] is None
            assert recovery["successor_journal_sha256"] is None

            journal_path = Path(str(external["final_path"]))
            journal_raw = journal_path.read_bytes()
            journal = json.loads(journal_raw)
            assert journal["phase"] == "prepared"
            assert len(journal_raw) == recovery["planned_journal_successor_size"]
            assert "sha256:" + sha256(journal_raw).hexdigest() == (
                recovery["planned_journal_successor_sha256"]
            )
            assert not candidate_path.exists()
        elif label == expected[1]:
            assert recovery["expected_action"] == "bind_created_candidate"
            assert recovery["external_file_action"] is None
            assert recovery["planned_journal_successor_path"] is None
            assert recovery["planned_journal_successor_parent_identity"] is None
            assert recovery["planned_journal_successor_sha256"] is None
            assert recovery["successor_candidate_identity"] is None

            journal_path = Path(str(recovery["successor_journal_path"]))
            journal_raw = journal_path.read_bytes()
            assert json.loads(journal_raw)["phase"] == "prepared"
            assert len(recovery["successor_journal_identity"]) == 3
            assert "sha256:" + sha256(journal_raw).hexdigest() == (
                recovery["successor_journal_sha256"]
            )
            assert not candidate_path.exists()
        else:
            assert recovery["expected_action"] == "bind_created_candidate"
            assert recovery["external_file_action"] is None
            assert recovery["successor_candidate_identity"] is None
            assert recovery == snapshots[expected[1]]
            assert candidate_path.is_dir()
            assert list(candidate_path.iterdir()) == []

        snapshots[label] = recovery
        observed.append(label)

    result = controller._finalize_live_start(
        session_root=prepared.run_root,
        fault_hook=trace,
    )

    assert result.status == "LIVE_AND_MATCHED"
    assert observed == list(expected)
    assert fixture.profile.runtime_root.is_dir()
