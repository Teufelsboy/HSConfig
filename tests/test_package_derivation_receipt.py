from hashlib import sha256
from pathlib import Path

import pytest

import hsconfig.package_derivation_receipt as derivation_receipt
from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import read_json, write_json
from hsconfig.package_derivation_receipt import (
    build_package_derivation_receipt,
    build_package_derivation_receipt_from_view,
    build_package_authority_context,
    refresh_package_derivation_authority,
    verify_package_derivation_receipt,
    verify_package_derivation_receipt_from_view,
)
from hsconfig.package_model import DirectoryPackageView
from hsconfig.strict_package_validation import (
    validate_complete_package,
    validate_complete_package_from_view,
)
from hsconfig.validate_package import validate_config_package
from hsconfig.visionai_registry import SINGLE_CANDIDATE_REVIEW_REPORT_PATHS
from tests.helpers.current_apply_eligible_package import (
    write_current_apply_eligible_package,
)
from tests.starter_fixtures import build_shadowpriest_starter_fixture
from tests.test_optimized_start_authority import (
    _build_single_candidate_authority,
)


OPTIMIZED_START_REPORT_PATHS = (
    "reports/optimized_start/starter_context.json",
    "reports/optimized_start/candidate-1.json",
    "reports/optimized_start/candidate-2.json",
    "reports/optimized_start/candidate-3.json",
    "reports/optimized_start/starter_config_decision.json",
)


def _enable_optimized_start(package: Path) -> None:
    manifest_path = package / "reports" / "input_manifest.json"
    manifest = read_json(manifest_path)
    manifest["configuration_mode"] = "LLM_OPTIMIZED_START"
    write_json(manifest_path, manifest)
    fixture = build_shadowpriest_starter_fixture(
        package.parent / f"{package.name}-legacy-authority"
    )
    source_root = fixture.decision_path.parent
    for relative_path in OPTIMIZED_START_REPORT_PATHS:
        target = package / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / target.name).read_bytes())


def _enable_single_candidate_start(package: Path):
    fixture = _build_single_candidate_authority(
        package.parent / f"{package.name}-single-authority"
    )
    manifest_path = package / "reports" / "input_manifest.json"
    manifest = read_json(manifest_path)
    manifest.update(
        {
            "configuration_mode": "LLM_OPTIMIZED_START",
            "optimized_start_authority_schema": (
                "single_candidate_review_v1"
            ),
        }
    )
    write_json(manifest_path, manifest)
    for relative_path in SINGLE_CANDIDATE_REVIEW_REPORT_PATHS:
        target = package / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            (fixture.report_root / target.name).read_bytes()
        )
    return fixture


def test_empty_canonical_receipts_remain_nonblocking_diagnostics(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "package")
    bundle_path = package / "reports" / "guide_claim_bundle.json"
    bundle = read_json(bundle_path)
    bundle["canonical_source_receipts"] = []
    write_json(bundle_path, bundle)

    summary_path = package / "reports" / "operator_summary.json"
    summary = read_json(summary_path)
    summary["package_derivation"] = refresh_package_derivation_authority(
        package
    )
    summary["apply_policy"] = "ALLOWED_WITH_WARNINGS"
    summary["runtime_apply_allowed"] = True
    summary["runtime_apply_mode"] = "load_safe_apply"
    summary["runtime_apply_reason"] = "runtime_load_safe_package"
    write_json(summary_path, summary)

    context = build_package_authority_context(package)
    gate = evaluate_apply_gate(package)

    assert context["canonical_receipt_count"] == 0
    assert context["exact_source_closed"] is False
    assert context["source_authority_verified"] is True
    assert gate["allowed"] is True
    assert gate["reasons"][1] == {
        "reason": "exact_source_not_closed",
        "blocking": False,
    }


def test_bound_canonical_receipt_projects_exact_source_closure(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "package")

    context = build_package_authority_context(package)

    assert context["canonical_receipt_count"] == 1
    assert context["exact_source_closed"] is True
    assert context["source_authority_verified"] is True


def test_optimized_receipt_binds_exact_five_starter_documents(
    tmp_path: Path,
) -> None:
    conservative = write_current_apply_eligible_package(
        tmp_path / "conservative"
    )
    optimized = write_current_apply_eligible_package(tmp_path / "optimized")
    _enable_optimized_start(optimized)

    conservative_receipt = build_package_derivation_receipt(conservative)
    conservative_view_receipt = build_package_derivation_receipt_from_view(
        DirectoryPackageView(conservative)
    )
    path_receipt = build_package_derivation_receipt(optimized)
    view_receipt = build_package_derivation_receipt_from_view(
        DirectoryPackageView(optimized)
    )

    assert conservative_receipt["schema_version"] == 2
    assert conservative_receipt == conservative_view_receipt
    assert not set(conservative_receipt["inputs"]).intersection(
        OPTIMIZED_START_REPORT_PATHS
    )
    assert path_receipt == view_receipt
    assert path_receipt["schema_version"] == 3
    assert set(path_receipt["inputs"]).intersection(
        OPTIMIZED_START_REPORT_PATHS
    ) == set(OPTIMIZED_START_REPORT_PATHS)


def test_optimized_receipt_rejects_each_starter_document_tamper(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "optimized")
    _enable_optimized_start(package)
    receipt = build_package_derivation_receipt(package)

    for relative_path in OPTIMIZED_START_REPORT_PATHS:
        target = package / relative_path
        original = target.read_bytes()
        payload = read_json(target)
        payload["tampered"] = True
        write_json(target, payload)

        path_valid, path_reasons = verify_package_derivation_receipt(
            package,
            receipt,
        )
        view_valid, view_reasons = verify_package_derivation_receipt_from_view(
            DirectoryPackageView(package),
            receipt,
        )

        assert path_valid is False
        assert view_valid is False
        assert path_reasons == view_reasons == [
            {
                "code": "package_derivation_mismatch",
                "detail": (
                    "Authoritative package content differs from its receipt."
                ),
            }
        ]
        target.write_bytes(original)


def test_schema_four_receipt_binds_snapshot_candidate_revision_review_and_confidence(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "single")
    fixture = _enable_single_candidate_start(package)

    path_receipt = build_package_derivation_receipt(package)
    view_receipt = build_package_derivation_receipt_from_view(
        DirectoryPackageView(package)
    )
    projection = derivation_receipt.single_candidate_review_derivation(
        package
    )

    assert path_receipt == view_receipt
    assert path_receipt["schema_version"] == (
        derivation_receipt.SINGLE_CANDIDATE_REVIEW_DERIVATION_RECEIPT_SCHEMA_VERSION
    )
    assert {
        path: path_receipt["inputs"][path]
        for path in SINGLE_CANDIDATE_REVIEW_REPORT_PATHS
    } == {
        path: "sha256:" + sha256((package / path).read_bytes()).hexdigest()
        for path in SINGLE_CANDIDATE_REVIEW_REPORT_PATHS
    }
    assert projection == {
        "optimized_start_authority_schema": "single_candidate_review_v1",
        "input_snapshot_manifest_sha256": (
            fixture.frozen.manifest.document.content_sha256
        ),
        "candidate_sha256": fixture.candidate.document.content_sha256,
        "candidate_revision": fixture.candidate.candidate_revision,
        "review_sha256": fixture.review.content_sha256,
        "review_status": "approved",
        "confidence": "high",
    }


def test_schema_four_receipt_rejects_each_authority_document_tamper(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "single")
    _enable_single_candidate_start(package)
    receipt = build_package_derivation_receipt(package)

    for relative_path in SINGLE_CANDIDATE_REVIEW_REPORT_PATHS:
        target = package / relative_path
        original = target.read_bytes()
        target.write_bytes(original[:-1] + b" ")

        path_valid, path_reasons = verify_package_derivation_receipt(
            package,
            receipt,
        )
        view_valid, view_reasons = verify_package_derivation_receipt_from_view(
            DirectoryPackageView(package),
            receipt,
        )
        assert path_valid is False
        assert view_valid is False
        assert path_reasons == view_reasons
        with pytest.raises(ValueError):
            build_package_derivation_receipt(package)
        target.write_bytes(original)


def test_legacy_schema_three_receipt_remains_valid(tmp_path: Path) -> None:
    package = write_current_apply_eligible_package(tmp_path / "legacy")
    _enable_optimized_start(package)

    receipt = build_package_derivation_receipt(package)
    from_view = build_package_derivation_receipt_from_view(
        DirectoryPackageView(package)
    )

    assert receipt == from_view
    assert receipt["schema_version"] == 3
    assert verify_package_derivation_receipt(package, receipt) == (True, [])
    assert derivation_receipt.legacy_optimized_start_derivation_digests(
        package
    ) == derivation_receipt.optimized_start_derivation_digests(package)


def test_receipt_schema_is_selected_only_from_manifest_discriminator(
    tmp_path: Path,
) -> None:
    conservative = write_current_apply_eligible_package(
        tmp_path / "conservative"
    )
    legacy = write_current_apply_eligible_package(tmp_path / "legacy")
    single = write_current_apply_eligible_package(tmp_path / "single")
    _enable_optimized_start(legacy)
    _enable_single_candidate_start(single)

    assert build_package_derivation_receipt(conservative)["schema_version"] == 2
    assert build_package_derivation_receipt(legacy)["schema_version"] == 3
    assert build_package_derivation_receipt(single)["schema_version"] == 4

    manifest_path = single / "reports" / "input_manifest.json"
    manifest = read_json(manifest_path)
    manifest.pop("optimized_start_authority_schema")
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError):
        build_package_derivation_receipt(single)


def test_conservative_downgrade_cannot_refresh_retained_single_candidate_reports(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "single")
    _enable_single_candidate_start(package)
    receipt = build_package_derivation_receipt(package)
    receipt_path = package / derivation_receipt.DERIVATION_RECEIPT_PATH
    derivation_receipt.write_package_derivation_receipt(
        receipt_path,
        receipt,
    )
    original_receipt_bytes = receipt_path.read_bytes()

    manifest_path = package / "reports" / "input_manifest.json"
    manifest = read_json(manifest_path)
    manifest["configuration_mode"] = "CONSERVATIVE"
    manifest.pop("optimized_start_authority_schema")
    write_json(manifest_path, manifest)
    assert all(
        (package / relative_path).is_file()
        for relative_path in SINGLE_CANDIDATE_REVIEW_REPORT_PATHS
    )

    with pytest.raises(ValueError):
        build_package_derivation_receipt(package)
    with pytest.raises(ValueError):
        build_package_derivation_receipt_from_view(
            DirectoryPackageView(package)
        )
    with pytest.raises(
        ValueError,
        match="^optimized_start_derivation_invalid$",
    ):
        refresh_package_derivation_authority(package)
    assert receipt_path.read_bytes() == original_receipt_bytes


def test_swapped_legacy_candidate_paths_fail_identically_everywhere(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "legacy")
    _enable_optimized_start(package)
    first = package / OPTIMIZED_START_REPORT_PATHS[1]
    second = package / OPTIMIZED_START_REPORT_PATHS[2]
    first_bytes = first.read_bytes()
    second_bytes = second.read_bytes()
    first.write_bytes(second_bytes)
    second.write_bytes(first_bytes)

    path_strict = validate_complete_package(package)
    view_strict = validate_complete_package_from_view(
        DirectoryPackageView(package)
    )
    public = validate_config_package(
        package,
        configuration_mode="LLM_OPTIMIZED_START",
        require_complete_package=True,
    )

    assert "optimized_start_authority_invalid" in path_strict["errors"]
    assert "optimized_start_authority_invalid" in view_strict["errors"]
    assert "optimized_start_authority_invalid" in public["errors"]
    with pytest.raises(ValueError):
        build_package_derivation_receipt(package)
    with pytest.raises(ValueError):
        build_package_derivation_receipt_from_view(
            DirectoryPackageView(package)
        )
