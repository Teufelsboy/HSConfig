from __future__ import annotations

from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import stat
import sys
from typing import Callable, Mapping

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import runtime_apply, runtime_installer
from hsconfig.current_output import resolve_current_package
from hsconfig.live_start_session import load_live_start_session
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    operator_profile_path,
)
from hsconfig.package_io import path_identity
from hsconfig.runtime_package_match import build_runtime_package_match_report
from hsconfig.runtime_state import read_runtime_state
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
)
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _join_hard_kill_process,
    _persist_worker_oracle,
)


_HARD_EXIT = 93


def _tree_evidence(root: Path) -> dict[str, tuple[tuple[int, int, int], bytes | None]]:
    assert root.is_dir() and not root.is_symlink()
    paths = (root, *sorted(root.rglob("*")))
    evidence: dict[str, tuple[tuple[int, int, int], bytes | None]] = {}
    for path in paths:
        status = path.lstat()
        assert not path.is_symlink()
        relative = "." if path == root else path.relative_to(root).as_posix()
        if stat.S_ISDIR(status.st_mode):
            payload = None
        else:
            assert stat.S_ISREG(status.st_mode) and status.st_nlink == 1
            payload = path.read_bytes()
        evidence[relative] = (path_identity(path), payload)
    return evidence


def _file_evidence(path: Path) -> tuple[tuple[int, int, int], bytes]:
    status = path.lstat()
    assert stat.S_ISREG(status.st_mode)
    assert status.st_nlink == 1
    assert not path.is_symlink()
    return path_identity(path), path.read_bytes()


def _legacy_bootstrap_hard_kill_worker(
    output_root_text: str,
    runtime_root_text: str,
    local_app_data: str,
    oracle_path_text: str,
) -> None:
    os.environ["LOCALAPPDATA"] = local_app_data
    output_root = Path(output_root_text)
    runtime_root = Path(runtime_root_text)
    oracle_path = Path(oracle_path_text)
    assert not runtime_root.exists()

    observed = {
        "bootstrap_calls": 0,
        "plan_calls": 0,
        "install_facade_calls": 0,
        "install_core_calls": 0,
        "layout_directory_calls": 0,
    }
    code_to_counter = {
        runtime_apply._bootstrap_legacy_runtime_root_from_context.__code__: (
            "bootstrap_calls"
        ),
        runtime_apply.plan_runtime_install.__code__: "plan_calls",
        runtime_apply.install_runtime_package.__code__: "install_facade_calls",
        runtime_installer._install_runtime_package_under_output_operation.__code__: (
            "install_core_calls"
        ),
        runtime_installer.bootstrap_runtime_layout_directory_from_pair.__code__: (
            "layout_directory_calls"
        ),
    }

    def observe(
        frame: object, event: str, argument: object
    ) -> Callable[..., object] | None:
        code = getattr(frame, "f_code", None)
        counter = code_to_counter.get(code)
        if event == "call" and counter is not None:
            observed[counter] += 1
        if (
            event != "return"
            or code
            is not runtime_apply._bootstrap_legacy_runtime_root_from_context.__code__
        ):
            return observe

        evidence = argument
        assert isinstance(evidence, runtime_apply.LegacyRuntimeRootBootstrapEvidence)
        assert evidence.runtime_root == runtime_root
        assert evidence.predecessor_state == "absent"
        assert evidence.predecessor_identity is None
        assert evidence.successor_identity == path_identity(runtime_root)
        assert evidence.created_directory_identities == (evidence.successor_identity,)
        assert runtime_root.is_dir() and not runtime_root.is_symlink()
        assert tuple(runtime_root.iterdir()) == ()
        assert observed == {
            "bootstrap_calls": 1,
            "plan_calls": 0,
            "install_facade_calls": 0,
            "install_core_calls": 0,
            "layout_directory_calls": 0,
        }
        sys.setprofile(None)
        _persist_worker_oracle(
            oracle_path,
            {
                "runtime_root_identity": evidence.successor_identity,
                "bound_ancestor_path": str(evidence.bound_ancestor_path),
                "bound_ancestor_identity": evidence.bound_ancestor_identity,
                "created_directory_identities": (evidence.created_directory_identities),
                "counts": observed,
            },
        )
        os._exit(_HARD_EXIT)

    previous_profile = sys.getprofile()
    sys.setprofile(observe)
    try:
        runtime_apply.apply_package(
            package_root=output_root,
            runtime_root=runtime_root,
        )
    finally:
        sys.setprofile(previous_profile)
    os._exit(94)


def _observed_public_apply(
    *,
    output_root: Path,
    runtime_root: Path,
) -> tuple[dict[str, object], dict[str, int]]:
    counts = {
        "public_apply": 0,
        "plan": 0,
        "install_facade": 0,
        "install_core": 0,
    }
    code_to_counter = {
        runtime_apply.apply_package.__code__: "public_apply",
        runtime_apply.plan_runtime_install.__code__: "plan",
        runtime_apply.install_runtime_package.__code__: "install_facade",
        runtime_installer._install_runtime_package_under_output_operation.__code__: (
            "install_core"
        ),
    }

    def observe(
        frame: object, event: str, _argument: object
    ) -> Callable[..., object] | None:
        counter = code_to_counter.get(getattr(frame, "f_code", None))
        if event == "call" and counter is not None:
            counts[counter] += 1
        return observe

    previous_profile = sys.getprofile()
    sys.setprofile(observe)
    try:
        result = runtime_apply.apply_package(
            package_root=output_root,
            runtime_root=runtime_root,
        )
    finally:
        sys.setprofile(previous_profile)
    assert isinstance(result, dict)
    return result, counts


def _assert_publication_is_unchanged(
    *,
    output_root: Path,
    output_before: Mapping[str, object],
    session_root: Path,
    session_before: Mapping[str, object],
    profile_before: tuple[tuple[int, int, int], bytes],
) -> None:
    assert _tree_evidence(output_root) == output_before
    assert _tree_evidence(session_root) == session_before
    assert _file_evidence(operator_profile_path()) == profile_before


def _assert_matched(package: Path, runtime_root: Path) -> Mapping[str, object]:
    report = build_runtime_package_match_report(
        package_root=package,
        runtime_root=runtime_root,
    )
    assert report["status"] == "matched"
    assert report["runtime_mapping_identity_valid"] is True
    assert report["runtime_tree_identity_valid"] is True
    assert report["missing_in_runtime"] == []
    assert report["extra_in_runtime"] == []
    assert report["semantic_mismatch_count"] == 0
    return report


def _committed_authority(
    *,
    runtime_root: Path,
    package_content_root: str,
    result: Mapping[str, object],
) -> tuple[
    dict[str, tuple[tuple[int, int, int], bytes | None]],
    Path,
    tuple[tuple[int, int, int], bytes],
    dict[str, object],
]:
    journals = load_runtime_transaction_journals(runtime_root)
    assert len(journals) == 1
    owner = journals[0]
    assert owner.phase is RuntimeTransactionPhase.FINALIZED
    assert owner.owns_target is True
    assert owner.source_manifest_sha256 == package_content_root
    assert owner.package_root_sha256 == result["package_root_sha256"]
    target = runtime_root / owner.target_path
    assert target.is_dir() and path_identity(target) == owner.target_identity

    state = read_runtime_state(runtime_root)
    assert state is not None and len(state.decks) == 1
    deck = state.decks[0]
    assert deck.state_key == owner.state_key
    assert deck.deck_name == owner.deck_name
    assert deck.config_dir == owner.next_config_dir
    assert deck.package_root_sha256 == owner.package_root_sha256

    ini_path = runtime_root / "CustomConfig" / "deck_config.ini"
    state_path = runtime_root / ".hsconfig" / "state.json"
    journal_path = (
        runtime_root / ".hsconfig" / "transactions" / f"{owner.transaction_id}.json"
    )
    receipt_path = (
        runtime_root
        / ".hsconfig"
        / "receipts"
        / owner.state_key
        / "last_apply_receipt.json"
    )
    assert result["receipt_path"] == str(receipt_path)
    receipt_evidence = _file_evidence(receipt_path)
    receipt = json.loads(receipt_evidence[1])
    assert receipt == {
        "schema_version": 1,
        "state_key": owner.state_key,
        "deck_name": owner.deck_name,
        "logical_config_dir": owner.logical_config_dir,
        "config_dir": owner.next_config_dir,
        "package_root_sha256": owner.package_root_sha256,
        "source_manifest_sha256": package_content_root,
        "ini_sha256": sha256(ini_path.read_bytes()).hexdigest(),
    }
    stable = {
        "runtime_root": (path_identity(runtime_root), None),
        "target": (path_identity(target), None),
        **{
            f"target/{key}": value
            for key, value in _tree_evidence(target).items()
            if key != "."
        },
        "deck_config_ini": _file_evidence(ini_path),
        "runtime_state": _file_evidence(state_path),
        "owner_journal": _file_evidence(journal_path),
    }
    return stable, receipt_path, receipt_evidence, receipt


def test_absent_legacy_runtime_root_hard_kill_resumes_from_plain_empty_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(
        tmp_path / "pipeline",
        monkeypatch,
        preview=True,
    )
    preview = controller.finalize_live_start(session_root=prepared.run_root)
    assert preview.status == "PREVIEW_READY"
    preview_session = load_live_start_session(prepared.run_root)
    assert preview_session.terminal_status == "PREVIEW_READY"
    assert not tuple(fixture.profile.runtime_root.iterdir())

    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    package = resolve_current_package(output_root)
    current = json.loads((output_root / "current.json").read_bytes())
    package_content_root = str(current["content_root_sha256"])
    legacy_runtime = tmp_path / "legacy-runtime"
    assert not legacy_runtime.exists()

    output_before = _tree_evidence(output_root)
    session_before = _tree_evidence(prepared.run_root)
    profile_before = _file_evidence(operator_profile_path())
    oracle_path = tmp_path / "legacy-bootstrap-oracle.json"
    process = multiprocessing.get_context("spawn").Process(
        target=_legacy_bootstrap_hard_kill_worker,
        args=(
            str(output_root),
            str(legacy_runtime),
            os.environ["LOCALAPPDATA"],
            str(oracle_path),
        ),
    )
    process.start()
    _join_hard_kill_process(
        process,
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )

    oracle = json.loads(oracle_path.read_bytes())
    assert oracle["counts"] == {
        "bootstrap_calls": 1,
        "plan_calls": 0,
        "install_facade_calls": 0,
        "install_core_calls": 0,
        "layout_directory_calls": 0,
    }
    assert tuple(oracle["runtime_root_identity"]) == path_identity(legacy_runtime)
    assert oracle["created_directory_identities"] == [oracle["runtime_root_identity"]]
    assert legacy_runtime.is_dir() and not legacy_runtime.is_symlink()
    assert tuple(legacy_runtime.iterdir()) == ()
    assert not (legacy_runtime / ".hsconfig").exists()
    assert not (legacy_runtime / "CustomConfig").exists()
    _assert_publication_is_unchanged(
        output_root=output_root,
        output_before=output_before,
        session_root=prepared.run_root,
        session_before=session_before,
        profile_before=profile_before,
    )

    completed, completed_counts = _observed_public_apply(
        output_root=output_root,
        runtime_root=legacy_runtime,
    )
    assert completed_counts == {
        "public_apply": 1,
        "plan": 1,
        "install_facade": 1,
        "install_core": 1,
    }
    assert completed["status"] == "applied"
    assert completed["runtime_write_performed"] is True
    assert completed["mapped_deck_name"] == fixture.deck_name
    assert completed["logical_config_dir"] == "shadowpriest"
    assert completed["versioned_config_dir"].startswith("shadowpriest--sha256-")
    assert completed["package_root_sha256"] in completed["versioned_config_dir"]
    _assert_matched(package, legacy_runtime)
    stable_authority, receipt_path, receipt_before, receipt_payload = (
        _committed_authority(
            runtime_root=legacy_runtime,
            package_content_root=package_content_root,
            result=completed,
        )
    )
    _assert_publication_is_unchanged(
        output_root=output_root,
        output_before=output_before,
        session_root=prepared.run_root,
        session_before=session_before,
        profile_before=profile_before,
    )

    replay, replay_counts = _observed_public_apply(
        output_root=output_root,
        runtime_root=legacy_runtime,
    )
    assert replay_counts == completed_counts
    assert replay["status"] == "already_current"
    assert replay["runtime_write_performed"] is False
    assert replay["mapped_deck_name"] == completed["mapped_deck_name"]
    assert replay["logical_config_dir"] == completed["logical_config_dir"]
    assert replay["versioned_config_dir"] == completed["versioned_config_dir"]
    assert replay["package_root_sha256"] == completed["package_root_sha256"]
    assert replay["receipt_path"] == str(receipt_path)
    replay_authority, replay_receipt_path, receipt_after, replay_payload = (
        _committed_authority(
            runtime_root=legacy_runtime,
            package_content_root=package_content_root,
            result=replay,
        )
    )
    assert replay_authority == stable_authority
    assert replay_receipt_path == receipt_path
    assert replay_payload == receipt_payload
    assert receipt_after == receipt_before
    _assert_matched(package, legacy_runtime)
    _assert_publication_is_unchanged(
        output_root=output_root,
        output_before=output_before,
        session_root=prepared.run_root,
        session_before=session_before,
        profile_before=profile_before,
    )
