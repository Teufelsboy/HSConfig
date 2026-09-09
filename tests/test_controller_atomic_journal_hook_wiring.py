from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from hsconfig import live_start_controller as controller
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.package_io import path_identity
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved


_INNER_CLOSED_POINTS = (
    "after_generic_file_inner_temp_created",
    "after_generic_file_inner_temp_partial",
    "after_generic_file_inner_temp_full",
    "after_generic_file_inner_temp_flushed",
)
_STAGING_CLOSED_POINT = (
    LiveStartFaultPoint.AFTER_GENERIC_FILE_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS.value
)
_POSIX_LINK_POINT = (
    LiveStartFaultPoint.AFTER_BOUND_STAGING_POSIX_LINK_BEFORE_UNLINK.value
)


def _raw_held_session(session_root: Path) -> dict[str, object]:
    value = json.loads((session_root / "session.json").read_bytes())
    assert isinstance(value, dict)
    return value


def _assert_plain_file(path: Path) -> tuple[int, int, int]:
    status = path.lstat()
    assert stat.S_ISREG(status.st_mode)
    assert not path.is_symlink()
    return path_identity(path)


def test_real_controller_forwards_first_journal_atomic_boundaries_as_closed_points(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "run", monkeypatch)
    expected = (*_INNER_CLOSED_POINTS, _STAGING_CLOSED_POINT)
    observed: list[str] = []
    inner_identity: tuple[int, int, int] | None = None

    def trace(point: LiveStartFaultPoint) -> None:
        nonlocal inner_identity
        label = str(point)
        if label not in {*expected, _POSIX_LINK_POINT}:
            return

        persisted = _raw_held_session(prepared.run_root)
        if persisted["phase"] != "APPLY_STARTED":
            return
        assert persisted["pending_transition"] is None
        recovery = persisted["apply_recovery"]
        if not isinstance(recovery, dict):
            return
        external = recovery["external_file_action"]
        if not isinstance(external, dict):
            return

        planned_journal = (
            recovery["expected_action"] == "materialize_file_action_staging"
            and recovery["install_route"] == "new_target"
            and recovery["planned_journal_successor_phase"] == "PREPARED"
            and recovery["successor_journal_path"] is None
            and recovery["successor_journal_identity"] is None
            and recovery["successor_journal_sha256"] is None
            and external["stage"] == "PLANNED"
            and external["action_kind"] == "materialize_file_action_staging"
            and external["commit_mode"] == "create_no_replace"
            and external["predecessor_state"] == "absent"
            and external["final_path"] == recovery["planned_journal_successor_path"]
            and external["planned_successor_size"]
            == recovery["planned_journal_successor_size"]
            and external["planned_successor_sha256"]
            == recovery["planned_journal_successor_sha256"]
        )
        bound_journal = (
            recovery["expected_action"]
            == "advance_controller_transaction_journal_write"
            and recovery["install_route"] == "new_target"
            and recovery["planned_journal_successor_phase"] == "PREPARED"
            and recovery["successor_journal_path"] is None
            and recovery["successor_journal_identity"] is None
            and recovery["successor_journal_sha256"] is None
            and external["stage"] == "STAGING_BOUND"
            and external["action_kind"]
            == "advance_controller_transaction_journal_write"
            and external["commit_mode"] == "create_no_replace"
            and external["predecessor_state"] == "absent"
            and external["final_path"] == recovery["planned_journal_successor_path"]
        )
        if label == _POSIX_LINK_POINT:
            if not bound_journal:
                return
        elif not planned_journal:
            return

        assert recovery["recovery_stage"] == "ACTIVE"
        assert recovery["runtime_match_status"] == "not_run"
        assert recovery["successor_candidate_identity"] is None
        fence_path = Path(str(recovery["successor_attempt_record_path"]))
        fence = json.loads(fence_path.read_bytes())
        assert fence["state"] == "CANDIDATE_PLANNED"
        assert fence["candidate_identity"] is None

        final_path = Path(str(external["final_path"]))
        staging_path = Path(str(external["staging_path"]))
        inner_path = Path(str(external["inner_temp_path"]))
        assert staging_path == final_path.with_name(f"{final_path.name}.staged")
        assert inner_path == staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )

        if label in _INNER_CLOSED_POINTS:
            assert label not in observed
            assert not final_path.exists()
            assert not staging_path.exists()
            current_identity = _assert_plain_file(inner_path)
            assert inner_path.stat().st_nlink == 1
            if inner_identity is None:
                inner_identity = current_identity
            assert current_identity == inner_identity
            if label == _INNER_CLOSED_POINTS[0]:
                assert inner_path.stat().st_size == 0
            elif label == _INNER_CLOSED_POINTS[-1]:
                journal_raw = inner_path.read_bytes()
                assert len(journal_raw) == external["planned_successor_size"]
                assert (
                    "sha256:" + sha256(journal_raw).hexdigest()
                    == (external["planned_successor_sha256"])
                )
                assert json.loads(journal_raw)["phase"] == "prepared"
        elif label == _STAGING_CLOSED_POINT:
            assert label not in observed
            assert inner_identity is not None
            assert not final_path.exists()
            assert not inner_path.exists()
            assert _assert_plain_file(staging_path) == inner_identity
            assert staging_path.stat().st_nlink == 1
            journal_raw = staging_path.read_bytes()
            assert len(journal_raw) == external["planned_successor_size"]
            assert (
                "sha256:" + sha256(journal_raw).hexdigest()
                == (external["planned_successor_sha256"])
            )
            assert json.loads(journal_raw)["phase"] == "prepared"
        else:
            assert os.name == "posix"
            assert observed == list(expected)
            assert not inner_path.exists()
            staging_identity = tuple(external["staging_identity"])
            assert _assert_plain_file(staging_path) == staging_identity
            assert _assert_plain_file(final_path) == staging_identity
            assert staging_path.stat().st_nlink == 2
            assert final_path.stat().st_nlink == 2
            assert staging_path.read_bytes() == final_path.read_bytes()
            assert len(final_path.read_bytes()) == external["staging_size"]
            assert (
                "sha256:" + sha256(final_path.read_bytes()).hexdigest()
                == (external["staging_sha256"])
            )
        observed.append(label)

    result = controller._finalize_live_start(
        session_root=prepared.run_root,
        fault_hook=trace,
    )

    assert result.status == "LIVE_AND_MATCHED"
    expected_observed = [*expected]
    if os.name == "posix":
        expected_observed.append(_POSIX_LINK_POINT)
    assert observed == expected_observed
    assert fixture.profile.runtime_root.is_dir()
