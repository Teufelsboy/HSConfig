from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import output_publisher, runtime_installer
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    disable_operator_profile,
    enable_operator_profile,
    operator_profile_path,
)
from hsconfig.output_operation_admission import (
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
)
from hsconfig.package_io import path_lexists
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
    _physical_tree,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_terminal_retirement_hard_kills import (
    _assert_attempt_bindings,
    _assert_physical_state,
    _capture_terminal_baseline,
    _result_pair,
    _terminal_retirement_hard_kill_worker,
)
from tests.test_output_publisher import build_rendered_run


_HARD_EXIT = 93
_REJECTED_WRITERS = (
    ("legacy_install", "runtime_live_admission_blocks_runtime_mutation"),
    ("broad_recovery", "runtime_live_admission_blocks_runtime_mutation"),
    ("generic_publisher", "runtime_live_admission_blocks_publication"),
    ("profile_disable", "runtime_live_admission_blocks_profile_mutation"),
    ("profile_rebind", "runtime_live_admission_blocks_profile_mutation"),
    ("competing_preview", "runtime_live_admission_blocks_publication"),
)


def _runtime_mutation_entry_codes() -> dict[Any, str]:
    return {
        runtime_installer._ensure_runtime_layout.__code__: "ensure_layout",
        runtime_installer._recover_locked.__code__: "recover_locked",
        runtime_installer._install_locked.__code__: "install_locked",
        runtime_installer._copy_runtime_files.__code__: "copy_runtime_files",
        runtime_installer._write_journal.__code__: "write_journal",
        runtime_installer._write_selected_state.__code__: "write_selected_state",
        runtime_installer._write_receipt.__code__: "write_receipt",
    }


def _published_output_from_owner(
    *,
    owner: session.LiveStartSession,
) -> output_publisher.PublishedOutput:
    publication = owner.publication_binding
    if not isinstance(publication, Mapping):
        raise AssertionError("owner publication binding missing")
    output_root = Path(str(publication["output_child_path"]))
    revision_root = output_root / str(publication["revision"])
    return output_publisher.PublishedOutput(
        output_root=output_root,
        revision_root=revision_root,
        package_root=revision_root / "04_package",
        content_root_sha256=str(publication["content_root_sha256"]).removeprefix(
            "sha256:"
        ),
        reused_existing_revision=False,
    )


def _terminal_writer_probe(
    action: str,
    owner_session_root_text: str,
    competing_session_root_text: str,
    runtime_root_text: str,
    profile_sha256: str,
    rebound_runtime_text: str,
    rebound_output_text: str,
    publisher_source_text: str,
    oracle_path_text: str,
) -> None:
    owner_session_root = Path(owner_session_root_text)
    os.environ["LOCALAPPDATA"] = str(owner_session_root.parents[2])
    runtime_root = Path(runtime_root_text)
    apply_counts, previous_profile = _start_apply_entry_observer()
    apply_observer = sys.getprofile()
    mutation_codes = _runtime_mutation_entry_codes()
    mutation_counts = dict.fromkeys(mutation_codes.values(), 0)

    def observe(frame: Any, event: str, arg: Any) -> None:
        if apply_observer is not None:
            apply_observer(frame, event, arg)
        if event == "call" and frame.f_code in mutation_codes:
            mutation_counts[mutation_codes[frame.f_code]] += 1

    sys.setprofile(observe)
    oracle: dict[str, Any] = {
        "action": action,
        "apply_entry_counts": apply_counts,
        "runtime_mutation_counts": mutation_counts,
    }
    try:
        owner = session.load_live_start_session(
            owner_session_root,
            local_app_data_root=owner_session_root.parents[2],
        )
        published = _published_output_from_owner(owner=owner)
        if action == "legacy_install":
            plan = runtime_installer.plan_runtime_install(
                published_output=published,
                runtime_root=runtime_root,
            )
            result = runtime_installer.install_runtime_package(plan)
            oracle["status"] = result.status
        elif action == "broad_recovery":
            state = runtime_installer.recover_runtime_state(runtime_root)
            oracle["status"] = None if state is None else "present"
        elif action == "competing_preview":
            result = controller.finalize_live_start(
                session_root=Path(competing_session_root_text)
            )
            oracle["status"] = result.status
        elif action == "generic_publisher":
            rendered = build_rendered_run(Path(publisher_source_text), 29)
            result = output_publisher.publish_configure_run(
                rendered,
                published.output_root,
            )
            oracle["status"] = result.content_root_sha256
        elif action == "profile_disable":
            result = disable_operator_profile(
                expected_predecessor_sha256=profile_sha256
            )
            oracle["status"] = result.content_sha256
        elif action == "profile_rebind":
            result = enable_operator_profile(
                runtime_root=Path(rebound_runtime_text),
                output_base_root=Path(rebound_output_text),
                expected_predecessor_sha256=profile_sha256,
            )
            oracle["status"] = result.content_sha256
        else:
            raise AssertionError(f"unknown terminal writer probe: {action}")
    except Exception as error:
        oracle["error_type"] = type(error).__name__
        oracle["error_message"] = str(error)
    finally:
        sys.setprofile(previous_profile)
    _persist_worker_oracle(Path(oracle_path_text), oracle)


def _owner_surface_snapshot(
    *,
    runtime_root: Path,
    output_base_root: Path,
    session_root: Path,
    admission_path: Path,
) -> dict[str, Any]:
    return {
        "runtime_tree": _physical_tree(runtime_root),
        "output_tree": _physical_tree(output_base_root),
        "owner_session_tree": _physical_tree(session_root),
        "owner_results": _result_pair(session_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "runtime_admission": _file_fingerprint(admission_path),
    }


def test_terminal_result_fences_every_writer_until_owner_acknowledges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "owner", monkeypatch)
    session_root = prepared.run_root
    approved = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    frozen = _frozen_identity(approved)
    markers = tmp_path / "terminal-writer-fencing-oracles"
    markers.mkdir()

    terminal_kill_oracle = markers / "terminal-before-ack.json"
    _spawn_and_join(
        target=_terminal_retirement_hard_kill_worker,
        args=(
            str(session_root),
            LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK.value,
            str(terminal_kill_oracle),
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    kill_observation = json.loads(terminal_kill_oracle.read_bytes())
    assert kill_observation["fault_value"] == (
        LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK.value
    )
    assert kill_observation["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )

    interrupted = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert kill_observation["session"] == interrupted.to_value()
    assert _frozen_identity(interrupted) == frozen
    assert interrupted.terminal_status == "LIVE_AND_MATCHED"
    assert interrupted.terminal_retirement is None
    assert isinstance(interrupted.closed_apply_recovery_commitment, Mapping)
    acknowledgement = interrupted.attempt_acknowledgement
    assert isinstance(acknowledgement, Mapping)
    assert acknowledgement["journal_owns_target"] is True
    assert acknowledgement["acknowledgement_action"] == (
        "retain_target_owner_delete_fence"
    )
    runtime_root = fixture.profile.runtime_root
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    publication = interrupted.publication_binding
    assert isinstance(publication, Mapping)
    assert Path(str(publication["output_child_path"])) == output_root
    baseline = _capture_terminal_baseline(
        fixture=fixture,
        current=interrupted,
        session_root=session_root,
        output_root=output_root,
    )
    _assert_attempt_bindings(
        current=interrupted,
        baseline=baseline,
        session_root=session_root,
        owning=True,
    )
    _assert_physical_state(
        fixture=fixture,
        current=interrupted,
        baseline=baseline,
        output_root=output_root,
        point=LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK,
        owning=True,
        prior_owner=None,
    )
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.run_id == interrupted.run_id
    assert admission.apply_attempt_id == baseline.attempt_id
    assert admission.admission_path == Path(
        str(acknowledgement["runtime_admission_path"])
    )
    operation = interrupted.output_operation_admission_binding
    assert isinstance(operation, Mapping)
    assert operation["state"] == "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"
    operation_path = Path(str(operation["admission_path"]))
    assert operation_path == output_operation_admission_path()
    assert not path_lexists(operation_path)
    operation_surfaces = (
        operation_path,
        output_operation_admission_staging_path(),
        output_operation_admission_reserved_temp_path(),
    )
    assert not any(path_lexists(path) for path in operation_surfaces)

    # Prepare the same-output contender only after the owner's publication is
    # final.  The acquisition seam is the sole stub; every writer below is real.
    _competing_fixture, competing = _prepare_approved(
        tmp_path / "competing-preview",
        monkeypatch,
        preview=True,
        profile=fixture.profile,
    )
    rebound_runtime = tmp_path / "rebound-runtime"
    rebound_output = tmp_path / "rebound-output"
    rebound_runtime.mkdir()
    rebound_output.mkdir()
    rebound_runtime_tree = _physical_tree(rebound_runtime)
    rebound_output_tree = _physical_tree(rebound_output)
    fenced = _owner_surface_snapshot(
        runtime_root=runtime_root,
        output_base_root=fixture.profile.output_base_root,
        session_root=session_root,
        admission_path=admission.admission_path,
    )

    for ordinal, (action, expected_error) in enumerate(_REJECTED_WRITERS):
        marker = markers / f"{ordinal:02d}-{action}.json"
        _spawn_and_join(
            target=_terminal_writer_probe,
            args=(
                action,
                str(session_root),
                str(competing.run_root),
                str(runtime_root),
                fixture.profile.content_sha256,
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
            _owner_surface_snapshot(
                runtime_root=runtime_root,
                output_base_root=fixture.profile.output_base_root,
                session_root=session_root,
                admission_path=admission.admission_path,
            )
            == fenced
        )
        assert not path_lexists(operation_path)
        assert not any(path_lexists(path) for path in operation_surfaces)
        assert load_runtime_live_attempt_admission() == admission
        assert _physical_tree(rebound_runtime) == rebound_runtime_tree
        assert _physical_tree(rebound_output) == rebound_output_tree
        current = session.load_live_start_session(
            session_root,
            local_app_data_root=session_root.parents[2],
        )
        assert _frozen_identity(current) == frozen
        _assert_attempt_bindings(
            current=current,
            baseline=baseline,
            session_root=session_root,
            owning=True,
        )
        if action == "competing_preview":
            rejected_preview = session.load_live_start_session(
                competing.run_root,
                local_app_data_root=competing.run_root.parents[2],
            )
            assert rejected_preview.pending_transition is None
            assert rejected_preview.output_operation_admission_binding is None
            assert rejected_preview.output_child_binding is None
            assert rejected_preview.publication_binding is None
            assert rejected_preview.apply_invocation_sha256 is None
            assert rejected_preview.runtime_admission_binding is None

    owner_resume_marker = markers / "owner-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(session_root), str(owner_resume_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    owner_resume = json.loads(owner_resume_marker.read_bytes())
    assert owner_resume.pop("apply_entry_counts") == _expected_apply_entry_counts(
        recovery=1
    )
    assert owner_resume["status"] == "LIVE_AND_MATCHED"
    terminal = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert owner_resume["session_sha256"] == terminal.content_sha256
    assert _frozen_identity(terminal) == frozen
    _assert_attempt_bindings(
        current=terminal,
        baseline=baseline,
        session_root=session_root,
        owning=True,
    )
    assert _result_pair(session_root) == baseline.result_pair
    assert load_runtime_live_attempt_admission() is None
    assert not any(path_lexists(path) for path in operation_surfaces)
    _assert_physical_state(
        fixture=fixture,
        current=terminal,
        baseline=baseline,
        output_root=output_root,
        point=LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_UNLINK,
        owning=True,
        prior_owner=None,
    )
    terminal_session = _file_fingerprint(session_root / "session.json")
    terminal_runtime = _physical_tree(runtime_root)
    terminal_output = _physical_tree(fixture.profile.output_base_root)
    terminal_profile = _file_fingerprint(operator_profile_path())
    terminal_results = _result_pair(session_root)

    owner_replay_marker = markers / "owner-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(session_root), str(owner_replay_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    owner_replay = json.loads(owner_replay_marker.read_bytes())
    assert owner_replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert owner_replay == owner_resume
    assert _file_fingerprint(session_root / "session.json") == terminal_session
    assert _physical_tree(runtime_root) == terminal_runtime
    assert _physical_tree(fixture.profile.output_base_root) == terminal_output
    assert _file_fingerprint(operator_profile_path()) == terminal_profile
    assert _result_pair(session_root) == terminal_results == baseline.result_pair
    assert not any(path_lexists(path) for path in operation_surfaces)

    # The exact approved contender that was fenced can now publish a preview;
    # preview completion must not enter or change Runtime.
    preview_marker = markers / "competing-preview-after-release.json"
    _spawn_and_join(
        target=_terminal_writer_probe,
        args=(
            "competing_preview",
            str(session_root),
            str(competing.run_root),
            str(runtime_root),
            fixture.profile.content_sha256,
            str(rebound_runtime),
            str(rebound_output),
            str(tmp_path / "unused-publisher-source"),
            str(preview_marker),
        ),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    preview = json.loads(preview_marker.read_bytes())
    assert preview["action"] == "competing_preview"
    assert preview["status"] == "PREVIEW_READY"
    assert "error_type" not in preview
    assert "error_message" not in preview
    assert preview["apply_entry_counts"] == _expected_apply_entry_counts()
    assert preview["runtime_mutation_counts"] == dict.fromkeys(
        _runtime_mutation_entry_codes().values(),
        0,
    )
    assert _physical_tree(runtime_root) == terminal_runtime
    assert _file_fingerprint(operator_profile_path()) == terminal_profile
    assert _file_fingerprint(session_root / "session.json") == terminal_session
    assert _result_pair(session_root) == terminal_results
    assert not any(path_lexists(path) for path in operation_surfaces)
