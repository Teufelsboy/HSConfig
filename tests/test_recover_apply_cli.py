from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path

import pytest

from hsconfig import live_start_session, published_apply
from hsconfig.cli import main
from hsconfig.operator_profile import operator_profile_path
from hsconfig.published_apply import (
    ApplyAndMatchPublishedResult,
    PhysicalApplyDisposition,
)
from tests.test_apply_and_match_published import (
    _ATTEMPT_A,
    _composite,
    _copy_alternate_revision,
    _lease_published_capabilities,
    _point_value,
    _stage_alternate_publication,
)
from tests.test_configure_prepublication_apply import (
    _physical_tree,
    _prepare_pipeline,
)


def _closed_result(session_root: Path) -> ApplyAndMatchPublishedResult:
    attempt = session_root / "runtime" / "attempt.json"
    journal = session_root / "runtime" / "journal.json"
    owner = session_root / "runtime" / "owner.json"
    admission = session_root / "runtime" / "admission.json"
    return ApplyAndMatchPublishedResult(
        raw_apply_status="recovered",
        physical_disposition=PhysicalApplyDisposition.COMMITTED,
        runtime_match_status="matched",
        runtime_match_sha256="sha256:" + ("b" * 64),
        package_root_sha256="sha256:" + ("c" * 64),
        last_apply_receipt_sha256="sha256:" + ("d" * 64),
        runtime_state_sha256="sha256:" + ("e" * 64),
        deck_config_ini_sha256="sha256:" + ("f" * 64),
        retained_attempt_record_path=attempt,
        retained_attempt_record_identity=(1, 2, 3),
        retained_attempt_record_sha256="sha256:" + ("1" * 64),
        retained_journal_path=journal,
        retained_journal_identity=(4, 5, 6),
        retained_journal_sha256="sha256:" + ("2" * 64),
        retained_target_owner_journal_path=owner,
        retained_target_owner_journal_identity=(7, 8, 9),
        retained_target_owner_journal_sha256="sha256:" + ("3" * 64),
        runtime_admission_path=admission,
        runtime_admission_parent_identity=(10, 11, 12),
        runtime_admission_identity=(13, 14, 15),
        runtime_admission_sha256="sha256:" + ("4" * 64),
        terminal_status="LIVE_AND_MATCHED",
        error_code=None,
    )


def _forbid_broad_apply(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("recover-apply must not enter a broad apply path")


def _canonical_compact(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _reseal_canonical_document(document: Mapping[str, object]) -> bytes:
    unsigned = dict(document)
    unsigned.pop("content_sha256", None)
    return _canonical_compact(
        {
            **unsigned,
            "content_sha256": "sha256:"
            + sha256(_canonical_compact(unsigned)).hexdigest(),
        }
    )


def test_recover_apply_uses_only_exact_recorded_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_root = tmp_path / "runs" / "run-cli-recorded"
    session_root.mkdir(parents=True)
    calls: list[Path] = []

    def fake_recover_apply_attempt(*, session_root: Path):
        calls.append(session_root)
        return _closed_result(session_root)

    monkeypatch.setattr(
        "hsconfig.published_apply.recover_apply_attempt",
        fake_recover_apply_attempt,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_apply.apply_package",
        _forbid_broad_apply,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_installer.install_runtime_package",
        _forbid_broad_apply,
    )

    code = main(
        [
            "recover-apply",
            "--session",
            str(session_root),
            "--json",
        ]
    )

    assert code == 0
    assert calls == [session_root]
    assert json.loads(capsys.readouterr().out) == {
        "deck_config_ini_sha256": "sha256:" + ("f" * 64),
        "error_code": None,
        "last_apply_receipt_sha256": "sha256:" + ("d" * 64),
        "package_root_sha256": "sha256:" + ("c" * 64),
        "physical_disposition": "COMMITTED",
        "raw_apply_status": "recovered",
        "retained_attempt_record_identity": [1, 2, 3],
        "retained_attempt_record_path": str(
            session_root / "runtime" / "attempt.json"
        ),
        "retained_attempt_record_sha256": "sha256:" + ("1" * 64),
        "retained_journal_identity": [4, 5, 6],
        "retained_journal_path": str(
            session_root / "runtime" / "journal.json"
        ),
        "retained_journal_sha256": "sha256:" + ("2" * 64),
        "retained_target_owner_journal_identity": [7, 8, 9],
        "retained_target_owner_journal_path": str(
            session_root / "runtime" / "owner.json"
        ),
        "retained_target_owner_journal_sha256": "sha256:" + ("3" * 64),
        "runtime_admission_identity": [13, 14, 15],
        "runtime_admission_parent_identity": [10, 11, 12],
        "runtime_admission_path": str(
            session_root / "runtime" / "admission.json"
        ),
        "runtime_admission_sha256": "sha256:" + ("4" * 64),
        "runtime_match_sha256": "sha256:" + ("b" * 64),
        "runtime_match_status": "matched",
        "runtime_state_sha256": "sha256:" + ("e" * 64),
        "terminal_status": "LIVE_AND_MATCHED",
    }


def test_recover_apply_reports_exact_apply_not_started_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    with _lease_published_capabilities(prepared) as capabilities:
        session_root = prepared.session_root
        expected_session = capabilities.expected_session
        expected_session_root_identity = (
            capabilities.session_lease.session_root_identity
        )
    session_before = (session_root / "session.json").read_bytes()
    runtime_before = tuple(
        sorted(
            (
                path.relative_to(prepared.runtime_root).as_posix(),
                path.is_dir(),
                None if path.is_dir() else path.read_bytes(),
            )
            for path in prepared.runtime_root.rglob("*")
        )
    )

    monkeypatch.setattr(
        "hsconfig.runtime_apply.apply_package",
        _forbid_broad_apply,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_installer.install_runtime_package",
        _forbid_broad_apply,
    )

    code = main(
        [
            "recover-apply",
            "--session",
            str(session_root),
            "--json",
        ]
    )

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {
        "persisted_session_sha256": expected_session.content_sha256,
        "run_id": expected_session.run_id,
        "runtime_write_performed": False,
        "session_root": str(session_root),
        "session_root_identity": list(expected_session_root_identity),
        "status": "apply_not_started",
    }
    assert (session_root / "session.json").read_bytes() == session_before
    assert tuple(
        sorted(
            (
                path.relative_to(prepared.runtime_root).as_posix(),
                path.is_dir(),
                None if path.is_dir() else path.read_bytes(),
            )
            for path in prepared.runtime_root.rglob("*")
        )
    ) == runtime_before


def test_recover_apply_bootstraps_only_persistent_lock_and_never_creates_attempt_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_after_admission_bound(point: object) -> None:
        if _point_value(point) == "after_admission_bound_before_invocation_write":
            raise RuntimeError("crash-after-admission-bound")

    with _lease_published_capabilities(prepared) as capabilities:
        with pytest.raises(RuntimeError, match="^crash-after-admission-bound$"):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_after_admission_bound,
            ):
                pass

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    pending = interrupted.pending_transition
    assert pending is not None
    assert pending["stage"] == "PRIMARY_APPLIED"
    runtime_root = prepared.runtime_root
    control_root = runtime_root / ".hsconfig"
    apply_lock = control_root / "apply.lock"
    assert sorted(
        path.relative_to(runtime_root).as_posix()
        for path in runtime_root.rglob("*")
    ) == [".hsconfig", ".hsconfig/apply.lock"]
    apply_lock.unlink()
    control_root.rmdir()

    def stop_after_lock_bootstrap(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("stop-after-runtime-lock-bootstrap")

    monkeypatch.setattr(
        published_apply,
        "bootstrap_runtime_layout_directory_from_pair",
        stop_after_lock_bootstrap,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_apply.apply_package",
        _forbid_broad_apply,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_installer.install_runtime_package",
        _forbid_broad_apply,
    )

    code = main(
        [
            "recover-apply",
            "--session",
            str(prepared.session_root),
            "--json",
        ]
    )

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {
        "errors": ["stop-after-runtime-lock-bootstrap"],
        "status": "failed",
    }
    assert sorted(
        path.relative_to(runtime_root).as_posix()
        for path in runtime_root.rglob("*")
    ) == [".hsconfig", ".hsconfig/apply.lock"]
    assert apply_lock.read_bytes() == b""


@pytest.mark.parametrize(
    ("drift", "expected_error"),
    (
        ("receipt", "live_start_resume_artifact_drift"),
        ("profile", "published_apply_output_operation_binding_changed"),
        ("publication", "published_apply_package_binding_changed"),
        ("runtime", "runtime_committed_state_changed"),
    ),
)
def test_recover_apply_rejects_receipt_profile_publication_or_runtime_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    drift: str,
    expected_error: str,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    def crash_before_apply_committed(point: object) -> None:
        if _point_value(point) == "after_installer_return_before_apply_committed":
            raise RuntimeError("crash-before-cli-drift")

    with _lease_published_capabilities(prepared) as capabilities:
        output_root = capabilities.output_root
        with pytest.raises(
            RuntimeError,
            match="^crash-before-cli-drift$",
        ):
            with _composite(
                published_apply,
                capabilities,
                apply_attempt_id=_ATTEMPT_A,
                fault_hook=crash_before_apply_committed,
            ):
                pass

    interrupted = live_start_session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    recovery = interrupted.apply_recovery
    assert interrupted.phase is live_start_session.LiveStartPhase.APPLY_STARTED
    assert interrupted.pending_transition is None
    assert isinstance(recovery, Mapping)
    assert recovery["recovery_stage"] == "ACTIVE"
    assert recovery["expected_action"] is None
    assert recovery["stable_physical_disposition"] == "COMMITTED"
    assert recovery["runtime_match_status"] == "unknown"
    assert interrupted.apply_invocation_sha256 is not None
    assert (
        prepared.session_root / "receipts" / "apply_invocation.json"
    ).is_file()
    assert published_apply.load_runtime_live_attempt_admission() is not None

    if drift == "receipt":
        receipt_path = (
            prepared.session_root / "receipts" / "apply_invocation.json"
        )
        receipt = json.loads(receipt_path.read_bytes())
        run_id = receipt["run_id"]
        assert isinstance(run_id, str)
        receipt["run_id"] = (
            ("0" if run_id[0] != "0" else "1") + run_id[1:]
        )
        receipt_path.write_bytes(_reseal_canonical_document(receipt))
    elif drift == "profile":
        profile_path = operator_profile_path()
        profile = json.loads(profile_path.read_bytes())
        live_by_default = profile["live_by_default"]
        assert type(live_by_default) is bool
        profile["live_by_default"] = not live_by_default
        profile_path.write_bytes(_reseal_canonical_document(profile))
    elif drift == "publication":
        alternate_revision, alternate_current = _stage_alternate_publication(
            tmp_path / "alternate-current"
        )
        _copy_alternate_revision(
            source_revision=alternate_revision,
            output_root=output_root,
        )
        (output_root / "current.json").write_bytes(alternate_current)
    else:
        journal_path = Path(str(recovery["predecessor_journal_path"]))
        journal = json.loads(journal_path.read_bytes())
        state_key = journal["state_key"]
        assert isinstance(state_key, str)
        state_path = prepared.runtime_root / ".hsconfig" / "state.json"
        state = json.loads(state_path.read_bytes())
        decks = state["decks"]
        assert isinstance(decks, list)
        selected = next(
            row
            for row in decks
            if isinstance(row, dict) and row.get("state_key") == state_key
        )
        package_sha256 = selected["package_root_sha256"]
        assert isinstance(package_sha256, str) and len(package_sha256) == 64
        selected["package_root_sha256"] = (
            ("0" if package_sha256[0] != "0" else "1")
            + package_sha256[1:]
        )
        state_path.write_bytes(
            (
                json.dumps(
                    state,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
        )

    state_before = _physical_tree(prepared.local_app_data / "HSConfig")
    runtime_before = _physical_tree(prepared.runtime_root)
    output_before = _physical_tree(output_root)
    monkeypatch.setattr(
        "hsconfig.runtime_apply.apply_package",
        _forbid_broad_apply,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_apply.install_runtime_package",
        _forbid_broad_apply,
    )
    monkeypatch.setattr(
        "hsconfig.runtime_installer.install_runtime_package",
        _forbid_broad_apply,
    )

    code = main(
        [
            "recover-apply",
            "--session",
            str(prepared.session_root),
            "--json",
        ]
    )

    assert code == 1
    assert json.loads(capsys.readouterr().out) == {
        "errors": [expected_error],
        "status": "failed",
    }
    assert _physical_tree(prepared.local_app_data / "HSConfig") == state_before
    assert _physical_tree(prepared.runtime_root) == runtime_before
    assert _physical_tree(output_root) == output_before
