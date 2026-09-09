from __future__ import annotations

from types import SimpleNamespace

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.live_start_faults import no_live_start_fault
from hsconfig.package_io import hold_plain_directory, path_identity


def _work_and_pending(tmp_path):
    work_parent = tmp_path / "work"
    cleanup_parent = tmp_path / "cleanup"
    work_parent.mkdir()
    cleanup_parent.mkdir()
    work = {
        "work_parent_path": str(work_parent),
        "work_parent_identity": list(path_identity(work_parent)),
        "work_root": str(work_parent / "live-start-test"),
        "work_root_identity": [1, 2, 3],
        "work_tree_sha256": "sha256:" + "1" * 64,
        "cleanup_manifest_sha256": "sha256:" + "2" * 64,
        "cleanup_entry_count": 3,
    }
    pending = {
        "operation": "cleanup_prepublication",
        "stage": "CLEANUP_DELETING",
        "external_file_action": None,
        "cleanup_cursor": 3,
        "cleanup_entry_count": 3,
        "cleanup_inventory_path": str(cleanup_parent / "live-start-test.inventory.json"),
        "quarantine_path": str(cleanup_parent / "live-start-test.quarantine"),
        "cleanup_parent_identity": list(path_identity(cleanup_parent)),
        **work,
    }
    return work, pending, cleanup_parent


def _authority(current, changes):
    session._validate_update_authority(
        session=current,
        event="same_phase_cas",
        changes=changes,
        transition_authority=session._INTERNAL_TRANSITION_AUTHORITY,
    )


def test_cleanup_completion_requires_exact_finished_pending_authority(tmp_path):
    work, pending, _ = _work_and_pending(tmp_path)
    completed = session._completed_prepublication_work_binding(work, pending)
    session._validate_prepublication_work_binding(completed)
    current = SimpleNamespace(pending_transition=pending, prepublication_work_binding=work)
    _authority(current, {"pending_transition": None, "prepublication_work_binding": completed})
    for bad_pending in (None, {**pending, "cleanup_cursor": 2}, {**pending, "external_file_action": {"uncompleted": True}}):
        current.pending_transition = bad_pending
        with pytest.raises(session.SessionCapabilityError, match="cleanup"):
            _authority(current, {"pending_transition": None, "prepublication_work_binding": completed})


def test_cleanup_completion_is_immutable_and_binds_original_work(tmp_path):
    work, pending, _ = _work_and_pending(tmp_path)
    completed = session._completed_prepublication_work_binding(work, pending)
    current = SimpleNamespace(pending_transition=None, prepublication_work_binding=completed)
    with pytest.raises(session.SessionCapabilityError, match="cleanup"):
        _authority(current, {"prepublication_work_binding": work})
    with pytest.raises(session.SessionValidationError, match="cleanup"):
        session._validate_prepublication_work_binding({**completed, "work_tree_sha256": "sha256:" + "3" * 64})


def test_unchanged_frozen_work_binding_accepts_json_projection(tmp_path):
    work, _pending, _ = _work_and_pending(tmp_path)
    current = SimpleNamespace(pending_transition=None, prepublication_work_binding=session._freeze_mapping(work))
    session._validate_prepublication_cleanup_completion_successor(
        session=current, event="package_valid", changes={"prepublication_work_binding": work},
        internally_authorized=True,
    )


@pytest.mark.parametrize("completed", [False, True])
def test_absent_work_requires_durable_cleanup_completion(tmp_path, completed):
    work, pending, cleanup_parent = _work_and_pending(tmp_path)
    if completed:
        work = session._completed_prepublication_work_binding(work, pending)
    current = SimpleNamespace(
        pending_transition=None,
        prepublication_work_binding=work,
        phase=session.LiveStartPhase.PUBLICATION_COMMITTED,
        run_id="test",
    )
    with hold_plain_directory(tmp_path / "work") as work_guard, hold_plain_directory(cleanup_parent) as cleanup_guard:
        def resume():
            return controller._continue_prepublication_cleanup_under_guards(
                current=current, session_lease=None, fault_hook=no_live_start_fault,
                cleanup_parent=cleanup_parent, cleanup_parent_identity=path_identity(cleanup_parent),
                cleanup_parent_guard=cleanup_guard, work_parent_guard=work_guard,
            )
        if completed:
            assert resume() is current
            (cleanup_parent / "live-start-test.inventory.json").write_bytes(b"foreign")
            with pytest.raises(ValueError, match="foreign_residue"):
                resume()
        else:
            with pytest.raises(ValueError, match="work_root_identity_changed"):
                resume()
