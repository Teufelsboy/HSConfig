from __future__ import annotations

from pathlib import Path

import pytest

from hsconfig import live_start_session as session
from hsconfig import published_apply
from hsconfig.configure_run_model import (
    create_configure_run_model,
    render_configure_run_model,
)
from hsconfig.output_publisher import publish_configure_run
from hsconfig.package_io import path_identity
from hsconfig.runtime_apply import apply_package
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from tests.test_apply_and_match_published import (
    _ATTEMPT_B,
    _composite,
    _lease_published_capabilities,
)
from tests.test_configure_prepublication_apply import _physical_tree, _prepare_pipeline


def test_report_only_republication_resumes_closed_success_with_historical_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    current_model = prepared.run_model
    historical_stages = {
        artifact.relative_path: artifact.content
        for artifact in current_model.stage_artifacts
        if artifact.relative_path != "configure_summary.json"
    }
    research_path = next(
        path for path in historical_stages if path.startswith("03_research/")
    )
    # Diagnostic-stage whitespace changes the publication, not its package.
    historical_stages[research_path] += b"\n"
    historical_model = create_configure_run_model(
        package=current_model.package,
        stage_artifacts=historical_stages,
    )
    historical_rendered = render_configure_run_model(historical_model)
    current_rendered = render_configure_run_model(current_model)
    assert historical_model.package is current_model.package
    assert historical_rendered.content_root_sha256 != current_rendered.content_root_sha256
    assert {
        artifact.relative_path: artifact.content
        for artifact in historical_rendered.artifacts
        if artifact.relative_path.startswith("04_package/")
    } == {
        artifact.relative_path: artifact.content
        for artifact in current_rendered.artifacts
        if artifact.relative_path.startswith("04_package/")
    }

    # Install the historical owner through real publication and apply, before
    # the current controller acquires output-operation/runtime admission.
    historical_output = tmp_path / "historical-output"
    historical_publication = publish_configure_run(historical_rendered, historical_output)
    installed = apply_package(
        package_root=historical_output,
        runtime_root=prepared.runtime_root,
    )
    assert installed["status"] == "applied"
    historical_journals = load_runtime_transaction_journals(prepared.runtime_root)
    assert len(historical_journals) == 1
    owner = historical_journals[0]
    assert owner.phase is RuntimeTransactionPhase.FINALIZED
    assert owner.owns_target is True
    assert owner.source_manifest_sha256 == historical_publication.content_root_sha256
    owner_path = runtime_transaction_journal_path(prepared.runtime_root, owner.transaction_id)
    owner_before = (path_identity(owner_path), owner_path.read_bytes())
    target = prepared.runtime_root / owner.target_path
    custom_config_before = _physical_tree(prepared.runtime_root / "CustomConfig")

    with _lease_published_capabilities(prepared) as capabilities:
        assert capabilities.publication_content_root_sha256 == (
            "sha256:" + current_rendered.content_root_sha256
        )
        with _composite(
            published_apply, capabilities, apply_attempt_id=_ATTEMPT_B,
        ) as held:
            assert held.result.terminal_status == "ALREADY_LIVE"
            assert held.result.raw_apply_status == "already_current"
            assert held.result.runtime_match_status == "matched"
            assert held.result.physical_disposition.value == "COMMITTED"
            closed = held.updated_session
            assert closed.phase is session.LiveStartPhase.RUNTIME_MATCHED
            assert closed.apply_recovery is not None
            assert closed.apply_recovery["recovery_stage"] == "CLOSED"
            assert closed.result_intent is None
            assert closed.terminal_status is None
            acknowledgement = held.acknowledgement_evidence
            assert acknowledgement is not None
            assert acknowledgement.journal_owns_target is False
            assert acknowledgement.target_owner_journal_path == owner_path
            assert acknowledgement.target_path == target
            assert acknowledgement.target_identity == path_identity(target)

    # The genuine Held return leaves CLOSED without result intent. This tests
    # success reentry, not the separately declared CLOSED crash fault hook.
    persisted = session.load_live_start_session(prepared.session_root)
    assert persisted.canonical_json == closed.canonical_json
    assert persisted.result_intent is None
    journals = load_runtime_transaction_journals(prepared.runtime_root)
    assert len(journals) == 2
    attempt = next(row for row in journals if row.transaction_id == _ATTEMPT_B)
    assert attempt.phase is RuntimeTransactionPhase.FINALIZED
    assert attempt.owns_target is False
    assert attempt.transaction_id != owner.transaction_id
    assert attempt.source_manifest_sha256 == current_rendered.content_root_sha256
    assert attempt.source_manifest_sha256 != owner.source_manifest_sha256
    assert attempt.package_root_sha256 == owner.package_root_sha256
    assert attempt.target_path == owner.target_path
    assert attempt.target_identity == owner.target_identity
    assert acknowledgement.journal_path.is_file()
    assert acknowledgement.retention_fence_path.is_file()
    assert (path_identity(owner_path), owner_path.read_bytes()) == owner_before
    assert _physical_tree(prepared.runtime_root / "CustomConfig") == custom_config_before

    recovered = published_apply.recover_apply_attempt(session_root=prepared.session_root)
    terminal = session.load_live_start_session(prepared.session_root)
    # Before result intent is bound, public recovery reports recovered/matched;
    # it does not preserve the initial Held's already_current presentation.
    assert recovered.terminal_status == terminal.terminal_status == "LIVE_AND_MATCHED"
    assert recovered.raw_apply_status == "recovered"
    assert recovered.runtime_match_status == "matched"
    assert recovered.physical_disposition.value == "COMMITTED"
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.result_intent["apply_attempt_id"] == _ATTEMPT_B
    assert terminal.terminal_retirement["operation"] == "ack_success"
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert terminal.terminal_retirement["apply_attempt_id"] == _ATTEMPT_B
    assert not acknowledgement.journal_path.exists()
    assert not acknowledgement.retention_fence_path.exists()
    assert not acknowledgement.runtime_admission_path.exists()
    assert load_runtime_live_attempt_admission() is None
    assert (path_identity(owner_path), owner_path.read_bytes()) == owner_before
    assert load_runtime_transaction_journals(prepared.runtime_root) == historical_journals
    assert _physical_tree(prepared.runtime_root / "CustomConfig") == custom_config_before

    terminal_tree = _physical_tree(prepared.session_root)
    runtime_tree = _physical_tree(prepared.runtime_root)
    assert published_apply.recover_apply_attempt(session_root=prepared.session_root) == recovered
    assert _physical_tree(prepared.session_root) == terminal_tree
    assert _physical_tree(prepared.runtime_root) == runtime_tree
    assert load_runtime_live_attempt_admission() is None
