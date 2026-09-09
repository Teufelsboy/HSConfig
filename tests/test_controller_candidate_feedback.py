from __future__ import annotations

import os
import stat
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

import pytest

from hsconfig import live_start_controller as controller
from hsconfig.live_start_session import LiveStartPhase, load_live_start_session
from hsconfig.operator_profile import operator_profile_path
from hsconfig.package_io import path_identity_from_status
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_context import (
    StarterContext,
    build_single_candidate_starter_context,
)
from tests.test_live_start_controller import _prepared_run, _write_unsigned_document
from tests.test_starter_candidate import sealed_single_candidate


def _physical_tree(
    root: Path,
) -> dict[str, tuple[str, tuple[int, int, int], bytes | None]]:
    if not os.path.lexists(root):
        return {}
    rows: dict[str, tuple[str, tuple[int, int, int], bytes | None]] = {}
    for path in (root, *root.rglob("*")):
        status = path.lstat()
        relative = "." if path == root else path.relative_to(root).as_posix()
        if stat.S_ISDIR(status.st_mode):
            kind = "directory"
            content = None
        elif stat.S_ISREG(status.st_mode):
            kind = "file"
            content = path.read_bytes()
        else:
            raise AssertionError(f"unexpected candidate-feedback path: {path}")
        rows[relative] = (kind, path_identity_from_status(status), content)
    return rows


def _file_fingerprint(path: Path) -> tuple[tuple[int, int, int], bytes]:
    status = path.lstat()
    return path_identity_from_status(status), path.read_bytes()


def _diagnostic_without_digest(document: FrozenJsonDocument) -> dict[str, object]:
    value = document.to_value()
    value.pop("content_sha256")
    return value


def _remove_globalvalues_key(value: dict[str, Any]) -> None:
    value["globalvalues"].pop("FirstTurnValueWeight")


def _remove_card_disposition(value: dict[str, Any]) -> None:
    value["card_dispositions"].pop()


def _prepare_candidate(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[controller.LiveStartPreparation, StarterContext, Path]:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    prepared, frozen = _prepared_run(tmp_path, monkeypatch)
    context = build_single_candidate_starter_context(frozen)
    candidate = sealed_single_candidate(context, mutate=mutate)
    draft_path = tmp_path / "candidate.json"
    _write_unsigned_document(draft_path, candidate)
    return prepared, context, draft_path


def _assert_repeated_rejected_candidate_feedback(
    *,
    tmp_path: Path,
    prepared: controller.LiveStartPreparation,
    first: FrozenJsonDocument,
    expected_finding: str,
) -> None:
    run_root = prepared.run_root
    rejected = load_live_start_session(run_root)
    assert rejected.phase is LiveStartPhase.CANDIDATE_DRAFTED
    assert rejected.candidate_revision == 1
    assert rejected.revisions_used == 1
    assert rejected.pending_transition is None
    assert rejected.terminal_status is None
    assert rejected.publication_binding is None
    assert rejected.output_operation_admission_binding is None
    assert rejected.output_child_binding is None
    assert rejected.apply_invocation_sha256 is None
    assert rejected.runtime_admission_binding is None
    assert rejected.runtime_layout_bootstrap is None
    assert rejected.apply_recovery is None
    assert rejected.result_intent is None
    assert "starter/starter_config_candidate.json" in rejected.artifact_bindings
    assert "receipts/candidate_validation.json" not in rejected.artifact_bindings
    assert not (run_root / "receipts/candidate_validation.json").exists()
    assert _diagnostic_without_digest(first) == {
        "candidate_revision": 1,
        "diagnostic_kind": "live_start_candidate_validation",
        "findings": [expected_finding],
        "next_candidate_revision": 2,
        "revisions_used": 1,
        "schema_version": 1,
        "status": "revision_required",
    }

    run_tree = _physical_tree(run_root)
    runtime_tree = _physical_tree(tmp_path / "runtime")
    output_tree = _physical_tree(tmp_path / "outputs")
    profile_fingerprint = _file_fingerprint(operator_profile_path())
    for _ in range(2):
        resumed = controller.resume_live_start(session_root=run_root)
        assert isinstance(resumed, FrozenJsonDocument)
        assert resumed.canonical_json == first.canonical_json
        persisted = load_live_start_session(run_root)
        assert persisted.canonical_json == rejected.canonical_json
        assert persisted.content_sha256 == rejected.content_sha256
        assert persisted.session_identity == rejected.session_identity
        assert _physical_tree(run_root) == run_tree
        assert _physical_tree(tmp_path / "runtime") == runtime_tree
        assert _physical_tree(tmp_path / "outputs") == output_tree
        assert _file_fingerprint(operator_profile_path()) == profile_fingerprint
        assert not (run_root / "receipts/candidate_validation.json").exists()


@pytest.mark.parametrize(
    ("mutate", "expected_finding"),
    (
        (
            _remove_globalvalues_key,
            "starter_candidate_globalvalues_keys_invalid",
        ),
        (
            _remove_card_disposition,
            "starter_candidate_card_dispositions_invalid",
        ),
    ),
    ids=("missing-globalvalues-key", "missing-card-disposition"),
)
def test_candidate_semantic_failure_returns_exact_repeatable_bounded_finding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Callable[[dict[str, Any]], None],
    expected_finding: str,
) -> None:
    prepared, context, draft_path = _prepare_candidate(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mutate=mutate,
    )

    first = controller.validate_live_start_candidate(
        session_root=prepared.run_root,
        draft_path=draft_path,
    )
    _assert_repeated_rejected_candidate_feedback(
        tmp_path=tmp_path,
        prepared=prepared,
        first=first,
        expected_finding=expected_finding,
    )

    corrected = sealed_single_candidate(context, revision=2)
    corrected_path = tmp_path / "corrected-candidate.json"
    _write_unsigned_document(corrected_path, corrected)
    validation = controller.validate_live_start_candidate(
        session_root=prepared.run_root,
        draft_path=corrected_path,
    )
    assert _diagnostic_without_digest(validation) == {
        "candidate_revision": 2,
        "candidate_sha256": "sha256:" + sha256(corrected.canonical_json).hexdigest(),
        "findings": [],
        "receipt_kind": "candidate_validation",
        "run_id": prepared.run_root.name,
        "schema_version": 1,
        "starter_context_sha256": (
            "sha256:" + sha256(context.document.canonical_json).hexdigest()
        ),
        "status": "valid",
    }
    completed = load_live_start_session(prepared.run_root)
    assert completed.phase is LiveStartPhase.CANDIDATE_VALIDATED
    assert completed.candidate_revision == 2
    assert completed.revisions_used == 1
    assert completed.pending_transition is None
    assert (
        prepared.run_root / "starter/starter_config_candidate.json"
    ).read_bytes() == (corrected.canonical_json)
    assert (prepared.run_root / "starter/starter_context.json").read_bytes() == (
        context.document.canonical_json
    )
    assert (prepared.run_root / "receipts/candidate_validation.json").is_file()


def test_unknown_candidate_validator_error_is_bounded_and_repeatable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _context, draft_path = _prepare_candidate(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    occurrence = 0

    def fail_with_unbounded_internal_message(**_kwargs: object) -> None:
        nonlocal occurrence
        occurrence += 1
        raise ValueError(
            f"private-validator-detail-{occurrence}:" + ("sensitive" * 1024)
        )

    monkeypatch.setattr(
        controller,
        "_load_bound_candidate",
        fail_with_unbounded_internal_message,
    )
    first = controller.validate_live_start_candidate(
        session_root=prepared.run_root,
        draft_path=draft_path,
    )
    _assert_repeated_rejected_candidate_feedback(
        tmp_path=tmp_path,
        prepared=prepared,
        first=first,
        expected_finding="candidate_semantics_invalid",
    )
    assert b"private-validator-detail" not in first.canonical_json
    assert b"sensitive" not in first.canonical_json
