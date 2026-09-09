from __future__ import annotations

from pathlib import Path

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import published_apply
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import disable_operator_profile, operator_profile_path
from hsconfig.output_operation_admission import (
    lease_output_operation_admission,
    observe_output_operation_admission_under_lease,
    require_output_operation_allows_publication,
)
from hsconfig.runtime_installer import lease_runtime_apply
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import load_runtime_transaction_journals
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved


class PreparedStop(BaseException):
    pass


def _file_bytes(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


def test_crash_after_invocation_prepared_before_admission_rolls_back_without_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No orphan runtime fence; the owner's output-operation fence still applies."""
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    runtime_root = fixture.profile.runtime_root
    original_runtime = _file_bytes(runtime_root)
    profile_bytes = operator_profile_path().read_bytes()

    def stop(point: LiveStartFaultPoint) -> None:
        if point is LiveStartFaultPoint.AFTER_INVOCATION_PREPARED_BEFORE_ADMISSION:
            raise PreparedStop(point.value)

    with pytest.raises(PreparedStop, match="after_invocation_prepared_before_admission"):
        controller._finalize_live_start(session_root=prepared.run_root, fault_hook=stop)
    interrupted = session.load_live_start_session(prepared.run_root)
    pending = interrupted.pending_transition
    assert interrupted.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert pending["operation"] == "install_apply_invocation"
    assert pending["stage"] == "PREPARED"
    assert pending["source_phase"] == "PUBLICATION_COMMITTED"
    assert pending["target_phase"] == "APPLY_STARTED"
    assert len(pending["apply_attempt_id"]) == 32
    assert interrupted.apply_invocation_sha256 is None
    assert interrupted.runtime_admission_binding is None
    assert interrupted.runtime_layout_bootstrap is None
    assert interrupted.apply_recovery is None
    assert interrupted.result_intent is None
    assert interrupted.terminal_status is None
    assert load_runtime_live_attempt_admission() is None
    assert not (prepared.run_root / "receipts/apply_invocation.json").exists()
    for key in (
        "runtime_admission_path", "runtime_admission_staging_path",
        "runtime_admission_staging_inner_temp_path",
    ):
        assert not Path(pending[key]).exists()
    assert load_runtime_transaction_journals(runtime_root) == ()
    runtime_bytes = _file_bytes(runtime_root)
    # Neutral lock bootstrap is not a runtime configuration or attempt write.
    assert runtime_bytes == {**original_runtime, Path(".hsconfig/apply.lock"): b""}
    output_bytes = _file_bytes(fixture.profile.output_base_root)
    operation = interrupted.output_operation_admission_binding
    assert operation["state"] == "ACTIVE"
    operation_path = Path(operation["admission_path"])
    operation_bytes = operation_path.read_bytes()

    # The absence of runtime admission is not permission to cross the still
    # ACTIVE output-operation fence, even for a different publication root.
    with pytest.raises(ValueError, match="output_operation_admission_blocks_runtime_mutation"):
        with lease_runtime_apply(
            runtime_root, expected_root_identity=fixture.profile.runtime_root_identity,
        ):
            pytest.fail("generic runtime writer crossed the active output fence")
    with pytest.raises(ValueError, match="output_operation_admission_blocks_profile_mutation"):
        disable_operator_profile(expected_predecessor_sha256=fixture.profile.content_sha256)
    with lease_output_operation_admission() as lease:
        observed = observe_output_operation_admission_under_lease(lease)
        assert observed is not None
        with pytest.raises(ValueError, match="output_operation_admission_blocks_publication"):
            require_output_operation_allows_publication(
                lease=lease, output_root=tmp_path / "unrelated-output",
                output_root_identity=None,
            )
    assert _file_bytes(runtime_root) == runtime_bytes
    assert _file_bytes(fixture.profile.output_base_root) == output_bytes
    assert operator_profile_path().read_bytes() == profile_bytes
    assert operation_path.read_bytes() == operation_bytes
    assert (prepared.run_root / "session.json").read_bytes() == interrupted.canonical_json

    # Exercise the real bounded rollback, not a new controller apply after it.
    recovered = published_apply.recover_apply_attempt(session_root=prepared.run_root)
    assert isinstance(recovered, published_apply.RecoverApplyNotStarted)
    assert recovered.status == "apply_not_started"
    assert recovered.runtime_write_performed is False
    assert recovered.run_id == interrupted.run_id
    assert recovered.session_root == prepared.run_root
    rolled_back = session.load_live_start_session(prepared.run_root)
    assert rolled_back.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert rolled_back.pending_transition is None
    assert rolled_back.apply_invocation_sha256 is None
    assert rolled_back.runtime_admission_binding is None
    assert rolled_back.runtime_layout_bootstrap is None
    assert rolled_back.apply_recovery is None
    assert rolled_back.result_intent is None
    assert rolled_back.terminal_status is None
    assert rolled_back.publication_binding == interrupted.publication_binding
    assert rolled_back.output_operation_admission_binding == operation
    assert recovered.persisted_session_sha256 == rolled_back.content_sha256
    assert load_runtime_live_attempt_admission() is None
    assert load_runtime_transaction_journals(runtime_root) == ()
    assert _file_bytes(runtime_root) == runtime_bytes
    assert _file_bytes(fixture.profile.output_base_root) == output_bytes
    assert operator_profile_path().read_bytes() == profile_bytes
    assert operation_path.read_bytes() == operation_bytes
