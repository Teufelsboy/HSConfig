from __future__ import annotations

import json
from pathlib import Path

import pytest

import hsconfig.live_start_controller as controller
import hsconfig.live_start_session as session
from tests.test_live_start_controller import _prepared_run


@pytest.fixture
def intake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    local = tmp_path / "local"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    prepared, _ = _prepared_run(tmp_path, monkeypatch)
    with session.lease_live_start_session(prepared.run_root) as lease:
        current = session.load_live_start_session_under_lock(session_lease=lease)
        with monkeypatch.context() as fault:
            def stop(**kwargs):
                raise RuntimeError("intake prepared")
            fault.setattr(controller, "_continue_pending_document_install", stop)
            with pytest.raises(RuntimeError, match="intake prepared"):
                controller._install_session_documents(
                    session_lease=lease, current=current,
                    operation="install_candidate", final_event="initial_draft",
                    documents={
                        "starter/starter_config_candidate.json": b'{"candidate":1}',
                        "starter/starter_context.json": b'{"context":1}',
                    },
                )
    return prepared.run_root


def _primary(lease):
    current = session.load_live_start_session_under_lock(session_lease=lease)
    pending = session._thaw(current.pending_transition)
    pending.pop("content_sha256")
    pending["stage"] = "PRIMARY_APPLIED"
    return session._transition_receipt_authorized_under_lock(
        session_lease=lease, expected_session=current, event="same_phase_cas",
        changes={"pending_transition": session._seal_pending(pending)},
    )


def _rewrite(root, mutate):
    path = root / "session.json"
    value = json.loads(path.read_bytes())
    value.pop("content_sha256")
    pending = value["pending_transition"]
    pending.pop("content_sha256")
    mutate(pending)
    pending["content_sha256"] = session._self_digest(pending)
    value["content_sha256"] = session._self_digest(value)
    path.write_bytes(session._canonical_json(value))


def test_active_reserved_temp_is_discarded_and_intake_resumes(intake):
    with session.lease_live_start_session(intake) as lease:
        current = _primary(lease)
        target = intake / current.pending_transition["actions"][0]["logical_path"]
        target.parent.mkdir(exist_ok=True)
        temp = target.with_name(f".{target.name}.live-start-atomic.tmp")
        temp.write_bytes(b"unbound crash bytes")
    with session.lease_live_start_session(intake) as lease:
        loaded = session.load_live_start_session_under_lock(session_lease=lease)
        done = controller._continue_pending_document_install(
            session_lease=lease, current=loaded, final_event="initial_draft"
        )
    assert done.phase is session.LiveStartPhase.CANDIDATE_DRAFTED
    assert done.pending_transition is None
    assert target.read_bytes() == b'{"candidate":1}'
    assert not temp.exists()


@pytest.mark.parametrize("stage,index", [("PREPARED", 0), ("PRIMARY_APPLIED", 1)])
def test_reserved_temp_for_nonactive_action_is_rejected(intake, stage, index):
    with session.lease_live_start_session(intake) as lease:
        current = (
            _primary(lease) if stage == "PRIMARY_APPLIED"
            else session.load_live_start_session_under_lock(session_lease=lease)
        )
        target = intake / current.pending_transition["actions"][index]["logical_path"]
        target.parent.mkdir(exist_ok=True)
        temp = target.with_name(f".{target.name}.live-start-atomic.tmp")
        temp.write_bytes(b"unbound")
    with pytest.raises(session.SessionLayoutError):
        session.load_live_start_session(intake)
    assert temp.read_bytes() == b"unbound"


def test_oversized_active_reserved_temp_is_not_deleted_or_promoted(intake):
    with session.lease_live_start_session(intake) as lease:
        current = _primary(lease)
        target = intake / current.pending_transition["actions"][0]["logical_path"]
        target.parent.mkdir(exist_ok=True)
        temp = target.with_name(f".{target.name}.live-start-atomic.tmp")
        temp.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        with pytest.raises(session.SessionConflictError):
            controller._continue_pending_document_install(
                session_lease=lease, current=current, final_event="initial_draft"
            )
    assert temp.exists()
    assert not target.exists()


@pytest.mark.parametrize("change", ["missing", "tampered"])
def test_completed_new_document_postcondition_is_required_on_load(intake, change):
    with session.lease_live_start_session(intake) as lease:
        current = _primary(lease)
        row = current.pending_transition["actions"][0]
        controller._materialize_pending_document(session_root=intake, current=current, row=row)
    _rewrite(intake, lambda pending: pending.update(next_action_index=1))
    target = intake / row["logical_path"]
    if change == "missing":
        target.unlink()
    else:
        target.write_bytes(b'{"tampered":1}')
    with pytest.raises((session.SessionConflictError, session.SessionValidationError)):
        session.load_live_start_session(intake)


@pytest.mark.parametrize("change", ["empty", "unknown_field", "wrong_stage", "source_name"])
def test_prepared_intake_requires_closed_intent_before_layout(intake, change):
    def mutate(pending):
        if change == "empty":
            pending["actions"] = []
        elif change == "unknown_field":
            pending["actions"][0]["unbound"] = True
        elif change == "wrong_stage":
            pending["stage"] = "CLEANUP_DELETING"
        else:
            source = Path(pending["actions"][0]["source_path"])
            pending["actions"][0]["source_path"] = str(source.with_name("wrong.json"))
    _rewrite(intake, mutate)
    with pytest.raises(session.SessionValidationError):
        session.load_live_start_session(intake)


def test_source_replacement_between_bound_stat_and_read_is_rejected(intake, monkeypatch):
    with session.lease_live_start_session(intake) as lease:
        current = _primary(lease)
        row = current.pending_transition["actions"][0]
        source = Path(row["source_path"])
        original_status = controller.plain_file_status
        replaced = False

        def replace_then_status(path):
            nonlocal replaced
            if path == source and not replaced:
                replaced = True
                payload = path.read_bytes()
                path.rename(path.with_suffix(".old"))
                path.write_bytes(payload)
            return original_status(path)

        monkeypatch.setattr(controller, "plain_file_status", replace_then_status)
        with pytest.raises((session.SessionConflictError, ValueError)):
            controller._materialize_pending_document(session_root=intake, current=current, row=row)
        assert not (intake / row["logical_path"]).exists()


def test_source_replacement_after_read_before_write_is_rejected(intake, monkeypatch):
    with session.lease_live_start_session(intake) as lease:
        current = _primary(lease)
        row = current.pending_transition["actions"][0]
        source = Path(row["source_path"])
        original_parent = controller._ensure_session_artifact_parent

        def replace_before_parent(**kwargs):
            payload = source.read_bytes()
            source.rename(source.with_suffix(".old"))
            source.write_bytes(payload)
            return original_parent(**kwargs)

        monkeypatch.setattr(controller, "_ensure_session_artifact_parent", replace_before_parent)
        with pytest.raises((session.SessionConflictError, ValueError)):
            controller._materialize_pending_document(session_root=intake, current=current, row=row)
        assert not (intake / row["logical_path"]).exists()


def test_final_phase_cas_rechecks_all_successor_bytes(intake, monkeypatch):
    with session.lease_live_start_session(intake) as lease:
        current = _primary(lease)
        original_transition = session._transition_receipt_authorized_under_lock

        def transition_and_remove(**kwargs):
            result = original_transition(**kwargs)
            pending = result.pending_transition
            if pending and pending["next_action_index"] == len(pending["actions"]):
                (intake / pending["actions"][0]["logical_path"]).unlink()
            return result

        monkeypatch.setattr(session, "_transition_receipt_authorized_under_lock", transition_and_remove)
        with pytest.raises((session.SessionConflictError, session.SessionValidationError)):
            controller._continue_pending_document_install(
                session_lease=lease, current=current, final_event="initial_draft"
            )


def _replacement_pending(intake, monkeypatch, *, payload=b'{"candidate":2}'):
    with session.lease_live_start_session(intake) as lease:
        current = session.load_live_start_session_under_lock(session_lease=lease)
        drafted = controller._continue_pending_document_install(
            session_lease=lease, current=current, final_event="initial_draft"
        )
    review = intake / "starter/starter_config_review.json"
    review.write_bytes(b'{"revision":"requested"}')
    value = drafted.to_value()
    value.pop("content_sha256")
    value["revisions_used"] = 1
    value["artifact_bindings"]["starter/starter_config_review.json"] = (
        session._bytes_sha256(review.read_bytes())
    )
    revised = session._seal_session_value(value, session_identity=drafted.session_identity)
    (intake / "session.json").write_bytes(revised.canonical_json)
    with session.lease_live_start_session(intake) as lease:
        current = session.load_live_start_session_under_lock(session_lease=lease)
        with monkeypatch.context() as fault:
            fault.setattr(
                controller, "_continue_pending_document_install", lambda **kwargs: None
            )
            controller._install_session_documents(
                session_lease=lease, current=current, operation="install_candidate",
                final_event="replacement_draft",
                documents={"starter/starter_config_candidate.json": payload},
            )
        _primary(lease)


def test_smaller_replacement_checks_predecessor_under_its_own_size_bound(intake, monkeypatch):
    _replacement_pending(intake, monkeypatch, payload=b'{}')
    with session.lease_live_start_session(intake) as lease:
        current = session.load_live_start_session_under_lock(session_lease=lease)
        done = controller._continue_pending_document_install(
            session_lease=lease, current=current, final_event="replacement_draft"
        )
    assert done.candidate_revision == 2
    assert (intake / "starter/starter_config_candidate.json").read_bytes() == b'{}'
    assert not (intake / "starter/starter_config_review.json").exists()


def test_completed_retirement_rejects_reappeared_predecessor(intake, monkeypatch):
    _replacement_pending(intake, monkeypatch)
    with session.lease_live_start_session(intake) as lease:
        current = session.load_live_start_session_under_lock(session_lease=lease)
        controller._materialize_pending_document(
            session_root=intake, current=current,
            row=current.pending_transition["actions"][0],
        )
        controller._retire_pending_document(
            session_root=intake, row=current.pending_transition["actions"][1],
            successor_bindings=current.pending_transition["successor_artifact_bindings"],
        )
    _rewrite(intake, lambda pending: pending.update(next_action_index=2))
    review = intake / "starter/starter_config_review.json"
    review.write_bytes(b'{"revision":"requested"}')
    with pytest.raises(session.SessionConflictError, match="reappeared"):
        session.load_live_start_session(intake)
