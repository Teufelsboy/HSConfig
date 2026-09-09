from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    operator_profile_path,
)
from hsconfig.output_operation_admission import (
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
)
from hsconfig.output_publisher import output_child_claim_path
from hsconfig.package_io import path_identity, path_lexists
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
)
from tests.test_codex_first_live_e2e import (
    _approve,
    _changed_candidate,
    _local_state,
    _matched_package,
    _prepare,
    _prepare_approved,
)
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _physical_tree,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _output_hard_kill_worker,
    _public_resume_worker,
    _spawn_and_join,
)
from tests.test_controller_terminal_retirement_hard_kills import _result_pair
from tests.test_controller_terminal_writer_fencing import (
    _runtime_mutation_entry_codes,
    _terminal_writer_probe,
)


_HARD_EXIT = 93
_FAULT = LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_BOUND
_REJECTED_WRITERS = (
    ("legacy_install", "output_operation_admission_blocks_runtime_mutation"),
    ("broad_recovery", "output_operation_admission_blocks_runtime_mutation"),
    ("generic_publisher", "output_operation_admission_blocks_publication"),
    ("profile_disable", "output_operation_admission_blocks_profile_mutation"),
    ("profile_rebind", "output_operation_admission_blocks_profile_mutation"),
    ("competing_preview", "live_start_output_operation_already_present"),
)


def _operation_surfaces() -> tuple[Path, Path, Path]:
    return (
        output_operation_admission_path(),
        output_operation_admission_staging_path(),
        output_operation_admission_reserved_temp_path(),
    )


def _fenced_surface(
    *,
    first_session_root: Path,
    owner_session_root: Path,
    runtime_root: Path,
    output_base_root: Path,
    admission_path: Path,
) -> dict[str, object]:
    return {
        "first_session": _physical_tree(first_session_root),
        "owner_session": _physical_tree(owner_session_root),
        "owner_results": _physical_tree(owner_session_root / "result"),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(output_base_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "admission": _file_fingerprint(admission_path),
    }


def _assert_no_unbound_operation_residue(*, admission_path: Path) -> None:
    active, staging, reserved = _operation_surfaces()
    assert active == admission_path
    assert path_lexists(active)
    assert not path_lexists(staging)
    assert not path_lexists(reserved)


def _assert_released_operation_surfaces() -> None:
    assert not any(path_lexists(path) for path in _operation_surfaces())


def _assert_competing_session_has_no_output_authority(
    *,
    competing_root: Path,
    frozen: Mapping[str, object],
) -> session.LiveStartSession:
    current = session.load_live_start_session(
        competing_root,
        local_app_data_root=competing_root.parents[2],
    )
    assert _frozen_identity(current) == frozen
    assert current.output_operation_admission_binding is None
    assert current.output_child_binding is None
    assert current.publication_binding is None
    assert current.apply_invocation_sha256 is None
    assert current.runtime_admission_binding is None
    assert current.runtime_layout_bootstrap is None
    assert current.apply_recovery is None
    assert current.result_intent is None
    assert current.terminal_status is None
    assert not tuple((competing_root / "result").glob("*"))
    return current


def test_active_output_operation_admission_fences_all_other_writers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)

    first_fixture, first = _prepare_approved(
        tmp_path / "published-preview",
        monkeypatch,
        preview=True,
    )
    first_result = controller.finalize_live_start(session_root=first.run_root)
    assert first_result.status == "PREVIEW_READY"
    first_terminal = session.load_live_start_session(
        first.run_root,
        local_app_data_root=first.run_root.parents[2],
    )
    assert first_terminal.terminal_status == "PREVIEW_READY"
    assert first_terminal.publication_binding is not None
    assert first_terminal.runtime_admission_binding is None
    assert not tuple(first_fixture.profile.runtime_root.iterdir())

    owner_fixture, owner = _prepare(
        tmp_path / "active-owner",
        monkeypatch,
        profile=first_fixture.profile,
    )
    owner_fixture = _changed_candidate(owner_fixture)
    _approve(tmp_path / "active-owner", owner_fixture, owner)
    competing_fixture, competing = _prepare_approved(
        tmp_path / "competing-preview",
        monkeypatch,
        preview=True,
        profile=first_fixture.profile,
    )
    del competing_fixture
    owner_approved = session.load_live_start_session(
        owner.run_root,
        local_app_data_root=owner.run_root.parents[2],
    )
    owner_frozen = _frozen_identity(owner_approved)
    competing_approved = session.load_live_start_session(
        competing.run_root,
        local_app_data_root=competing.run_root.parents[2],
    )
    competing_frozen = _frozen_identity(competing_approved)
    competing_initial_tree = _physical_tree(competing.run_root)

    markers = tmp_path / "output-writer-fencing-oracles"
    markers.mkdir()
    kill_marker = markers / "active-output-operation.json"
    _spawn_and_join(
        target=_output_hard_kill_worker,
        args=(str(owner.run_root), _FAULT.value, str(kill_marker)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    kill = json.loads(kill_marker.read_bytes())
    assert kill["fault_value"] == _FAULT.value
    assert kill["apply_entry_counts"] == _expected_apply_entry_counts()
    assert kill["phase"] == "PREPUBLICATION_CHECK_PASSED"
    assert kill["pending_operation"] is None
    kill_operation = kill["output_operation_admission_binding"]
    assert isinstance(kill_operation, Mapping)
    assert kill_operation["state"] == "ACTIVE"
    assert kill["output_child_binding"] is None
    assert kill["publication_binding"] is None
    assert kill["apply_invocation_sha256"] is None
    assert kill["runtime_admission_binding"] is None
    assert kill["runtime_layout_bootstrap"] is None
    assert kill["terminal_status"] is None

    interrupted = session.load_live_start_session(
        owner.run_root,
        local_app_data_root=owner.run_root.parents[2],
    )
    assert _frozen_identity(interrupted) == owner_frozen
    assert interrupted.pending_transition is None
    assert interrupted.phase.value == "PREPUBLICATION_CHECK_PASSED"
    operation = interrupted.output_operation_admission_binding
    assert isinstance(operation, Mapping)
    assert operation["state"] == "ACTIVE"
    assert operation["run_id"] == interrupted.run_id
    assert operation["session_root"] == str(owner.run_root)
    output_root = derive_deck_output_binding(
        first_fixture.profile,
        first_fixture.deck_name,
    ).output_root
    assert operation["output_child_path"] == str(output_root)
    assert operation["output_child_predecessor_state"] == "existing"
    assert tuple(operation["output_child_predecessor_identity"]) == path_identity(
        output_root
    )
    admission_path = Path(str(operation["admission_path"]))
    admission = _file_fingerprint(admission_path)
    assert admission == (
        tuple(operation["admission_identity"]),
        operation["admission_size"],
        operation["admission_sha256"],
    )
    assert path_identity(admission_path.parent) == tuple(
        operation["admission_parent_identity"]
    )
    assert interrupted.output_child_binding is None
    assert interrupted.publication_binding is None
    assert interrupted.apply_invocation_sha256 is None
    assert interrupted.runtime_admission_binding is None
    assert interrupted.runtime_layout_bootstrap is None
    assert interrupted.apply_recovery is None
    assert interrupted.result_intent is None
    assert interrupted.terminal_status is None
    assert not path_lexists(output_child_claim_path(output_root))
    _assert_no_unbound_operation_residue(admission_path=admission_path)
    assert load_runtime_live_attempt_admission() is None

    rebound_runtime = tmp_path / "rebound-runtime"
    rebound_output = tmp_path / "rebound-output"
    rebound_runtime.mkdir()
    rebound_output.mkdir()
    rebound_runtime_tree = _physical_tree(rebound_runtime)
    rebound_output_tree = _physical_tree(rebound_output)
    fenced = _fenced_surface(
        first_session_root=first.run_root,
        owner_session_root=owner.run_root,
        runtime_root=first_fixture.profile.runtime_root,
        output_base_root=first_fixture.profile.output_base_root,
        admission_path=admission_path,
    )

    for ordinal, (action, expected_error) in enumerate(_REJECTED_WRITERS):
        marker = markers / f"{ordinal:02d}-{action}.json"
        _spawn_and_join(
            target=_terminal_writer_probe,
            args=(
                action,
                str(first.run_root),
                str(competing.run_root),
                str(first_fixture.profile.runtime_root),
                first_fixture.profile.content_sha256,
                str(rebound_runtime),
                str(rebound_output),
                str(tmp_path / f"publisher-source-{ordinal}"),
                str(marker),
            ),
            expected_exitcode=0,
            timeout_seconds=360,
        )
        observed = json.loads(marker.read_bytes())
        assert observed["action"] == action
        assert observed["error_type"] == "ValueError"
        assert observed["error_message"] == expected_error
        assert "status" not in observed
        assert observed["apply_entry_counts"] == _expected_apply_entry_counts()
        assert observed["runtime_mutation_counts"] == dict.fromkeys(
            _runtime_mutation_entry_codes().values(),
            0,
        )
        assert (
            _fenced_surface(
                first_session_root=first.run_root,
                owner_session_root=owner.run_root,
                runtime_root=first_fixture.profile.runtime_root,
                output_base_root=first_fixture.profile.output_base_root,
                admission_path=admission_path,
            )
            == fenced
        )
        assert _physical_tree(rebound_runtime) == rebound_runtime_tree
        assert _physical_tree(rebound_output) == rebound_output_tree
        _assert_no_unbound_operation_residue(admission_path=admission_path)
        assert load_runtime_live_attempt_admission() is None
        current = session.load_live_start_session(
            owner.run_root,
            local_app_data_root=owner.run_root.parents[2],
        )
        assert current == interrupted
        assert _frozen_identity(current) == owner_frozen
        if action == "competing_preview":
            competing_after_rejection = (
                _assert_competing_session_has_no_output_authority(
                    competing_root=competing.run_root,
                    frozen=competing_frozen,
                )
            )
            assert competing_after_rejection.phase.value in {
                "REVIEW_APPROVED",
                "PACKAGE_VALIDATED",
                "PREPUBLICATION_CHECK_PASSED",
            }
        else:
            assert _physical_tree(competing.run_root) == competing_initial_tree

    resume_marker = markers / "owner-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(owner.run_root), str(resume_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resumed = json.loads(resume_marker.read_bytes())
    assert resumed.pop("apply_entry_counts") == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    assert resumed["status"] == "LIVE_AND_MATCHED"
    terminal = session.load_live_start_session(
        owner.run_root,
        local_app_data_root=owner.run_root.parents[2],
    )
    assert _frozen_identity(terminal) == owner_frozen
    assert terminal.terminal_status == "LIVE_AND_MATCHED"
    assert terminal.pending_transition is None
    assert terminal.apply_invocation_sha256 is not None
    assert isinstance(terminal.runtime_layout_bootstrap, Mapping)
    assert isinstance(terminal.runtime_admission_binding, Mapping)
    assert isinstance(terminal.result_intent, Mapping)
    assert terminal.result_intent["physical_disposition"] == "COMMITTED"
    assert terminal.result_intent["raw_apply_status"] == "applied"
    assert terminal.result_intent["runtime_match_status"] == "matched"
    attempt_id = str(terminal.runtime_layout_bootstrap["apply_attempt_id"])
    assert terminal.result_intent["apply_attempt_id"] == attempt_id
    invocation_path = owner.run_root / "receipts" / "apply_invocation.json"
    assert tuple(owner.run_root.rglob("*apply_invocation*.json")) == (invocation_path,)
    invocation = json.loads(invocation_path.read_bytes())
    assert invocation["apply_attempt_id"] == attempt_id
    assert invocation["content_sha256"] == terminal.apply_invocation_sha256
    assert (
        terminal.artifact_bindings["receipts/apply_invocation.json"]
        == (_file_fingerprint(invocation_path)[2])
    )

    published_output, package, runtime_target = _matched_package(owner_fixture)
    assert published_output == output_root
    assert (
        package == output_root / terminal.publication_binding["revision"] / "04_package"
    )
    journals = load_runtime_transaction_journals(first_fixture.profile.runtime_root)
    assert len(journals) == 1
    runtime_owner = journals[0]
    assert runtime_owner.transaction_id == attempt_id
    assert runtime_owner.phase is RuntimeTransactionPhase.FINALIZED
    assert runtime_owner.owns_target is True
    assert (
        first_fixture.profile.runtime_root / runtime_owner.target_path == runtime_target
    )
    assert path_identity(runtime_target) == runtime_owner.target_identity
    assert not Path(str(terminal.runtime_admission_binding["admission_path"])).exists()
    assert load_runtime_live_attempt_admission() is None
    _assert_released_operation_surfaces()
    assert not path_lexists(output_child_claim_path(output_root))

    terminal_owner_tree = _physical_tree(owner.run_root)
    terminal_first_tree = _physical_tree(first.run_root)
    terminal_results = _result_pair(owner.run_root)
    terminal_runtime = _physical_tree(first_fixture.profile.runtime_root)
    terminal_output = _physical_tree(first_fixture.profile.output_base_root)
    terminal_profile = _file_fingerprint(operator_profile_path())
    replay_marker = markers / "owner-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(owner.run_root), str(replay_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay = json.loads(replay_marker.read_bytes())
    assert replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay == resumed
    assert _physical_tree(owner.run_root) == terminal_owner_tree
    assert _physical_tree(first.run_root) == terminal_first_tree
    assert _result_pair(owner.run_root) == terminal_results
    assert _physical_tree(first_fixture.profile.runtime_root) == terminal_runtime
    assert _physical_tree(first_fixture.profile.output_base_root) == terminal_output
    assert _file_fingerprint(operator_profile_path()) == terminal_profile
    _assert_released_operation_surfaces()

    preview_marker = markers / "competing-preview-after-release.json"
    _spawn_and_join(
        target=_terminal_writer_probe,
        args=(
            "competing_preview",
            str(first.run_root),
            str(competing.run_root),
            str(first_fixture.profile.runtime_root),
            first_fixture.profile.content_sha256,
            str(rebound_runtime),
            str(rebound_output),
            str(tmp_path / "unused-publisher-source"),
            str(preview_marker),
        ),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    allowed_preview = json.loads(preview_marker.read_bytes())
    assert allowed_preview["action"] == "competing_preview"
    assert allowed_preview["status"] == "PREVIEW_READY"
    assert "error_type" not in allowed_preview
    assert "error_message" not in allowed_preview
    assert allowed_preview["apply_entry_counts"] == _expected_apply_entry_counts()
    assert allowed_preview["runtime_mutation_counts"] == dict.fromkeys(
        _runtime_mutation_entry_codes().values(),
        0,
    )
    competing_terminal = session.load_live_start_session(
        competing.run_root,
        local_app_data_root=competing.run_root.parents[2],
    )
    assert _frozen_identity(competing_terminal) == competing_frozen
    assert competing_terminal.terminal_status == "PREVIEW_READY"
    assert competing_terminal.apply_invocation_sha256 is None
    assert competing_terminal.runtime_admission_binding is None
    assert competing_terminal.runtime_layout_bootstrap is None
    assert competing_terminal.apply_recovery is None
    assert _physical_tree(first_fixture.profile.runtime_root) == terminal_runtime
    assert _physical_tree(owner.run_root) == terminal_owner_tree
    assert _physical_tree(first.run_root) == terminal_first_tree
    assert _result_pair(owner.run_root) == terminal_results
    assert _file_fingerprint(operator_profile_path()) == terminal_profile
    _assert_released_operation_surfaces()
