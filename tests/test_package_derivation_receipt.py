from pathlib import Path

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
from tests.helpers.current_apply_eligible_package import (
    write_current_apply_eligible_package,
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
    for index, relative_path in enumerate(OPTIMIZED_START_REPORT_PATHS, start=1):
        write_json(package / relative_path, {"frozen_document": index})


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
