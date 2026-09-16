"""Focused authority and real quality-route checks for the lean workflow."""

from dataclasses import replace
from pathlib import Path

import pytest

import hsconfig.live_start_controller as controller
from hsconfig.live_start_session import LiveStartPhase, load_live_start_session
from hsconfig.optimized_start_authority import load_optimized_start_authority
from hsconfig.package_model import DirectoryPackageView
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.runtime_package_match import build_runtime_package_match_report
from hsconfig.strict_package_validation import (
    validated_optimized_start_authority_from_view,
)
from tests.test_optimized_start_authority import (
    SINGLE_CANDIDATE_MANIFEST,
    _build_single_candidate_authority,
)
from tests.test_quality_live_start_controller import quality_request as _quality_request
from tests.test_quality_start_summary import _approved_quality


def test_view_cannot_downgrade_caller_authority_using_stored_manifest(tmp_path):
    """Break: re-read the stored v1 label and ignore a caller-v2 receipt."""
    fixture = _build_single_candidate_authority(tmp_path / "fixture")
    package = tmp_path / "package"
    reports = package / "reports" / "optimized_start"
    reports.mkdir(parents=True)
    for source in fixture.report_root.iterdir():
        (reports / source.name).write_bytes(source.read_bytes())
    (package / "reports/input_manifest.json").write_bytes(
        FrozenJsonDocument.from_value(SINGLE_CANDIDATE_MANIFEST).canonical_json
    )
    view = DirectoryPackageView(package)
    original = load_optimized_start_authority(
        report_root=reports, manifest=SINGLE_CANDIDATE_MANIFEST,
    )
    assert validated_optimized_start_authority_from_view(
        view, manifest=SINGLE_CANDIDATE_MANIFEST,
    ) == original

    # Five paths alone must not turn four genuine legacy documents into v2.
    (reports / "candidate_validation_receipt.json").write_bytes(b"{}")
    quality_manifest = {
        **SINGLE_CANDIDATE_MANIFEST,
        "optimized_start_authority_schema": "single_candidate_review_v2",
    }
    with pytest.raises(ValueError, match="^starter_document_schema_version_invalid$"):
        load_optimized_start_authority(report_root=reports, manifest=quality_manifest)
    with pytest.raises(ValueError, match="^starter_document_schema_version_invalid$"):
        validated_optimized_start_authority_from_view(view, manifest=quality_manifest)


@pytest.fixture
def quality_request(tmp_path, monkeypatch):
    return _quality_request.__wrapped__(tmp_path, monkeypatch)


def test_quality_live_flow_installs_matches_and_resumes_without_reapply(
    quality_request, tmp_path, monkeypatch,
):
    """Break: the established approved route cannot complete guarded installation."""
    request = replace(quality_request, preview_requested=False)
    prepared, context, candidate, receipt, _ = _approved_quality(request, tmp_path)
    assert context.document.to_value()["schema_version"] == 3
    assert candidate.document.to_value()["schema_version"] == 3
    assert receipt.to_value()["schema_version"] == 2
    result = controller.finalize_live_start(session_root=prepared.run_root)
    assert result.status == "LIVE_AND_MATCHED"
    completed = load_live_start_session(prepared.run_root)
    assert completed.schema_version == 2
    assert completed.phase is LiveStartPhase.RUNTIME_MATCHED
    assert completed.terminal_status == "LIVE_AND_MATCHED"
    assert completed.apply_recovery is None
    assert completed.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    published = completed.publication_binding
    package = Path(published["output_child_path"]) / published["revision"] / "04_package"
    report = build_runtime_package_match_report(
        package_root=package, runtime_root=tmp_path / "runtime",
    )
    assert report["status"] == "matched"

    def no_second_apply(**_):
        pytest.fail("completed session attempted another apply")

    monkeypatch.setattr(
        controller._published_apply, "_apply_and_match_published", no_second_apply,
    )
    repeated = controller.resume_live_start(session_root=prepared.run_root)
    assert repeated.summary.canonical_json == result.summary.canonical_json
