from pathlib import Path

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import read_json, write_json
from hsconfig.package_derivation_receipt import (
    build_package_authority_context,
    refresh_package_derivation_authority,
)
from tests.helpers.current_apply_eligible_package import (
    write_current_apply_eligible_package,
)


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
    write_json(summary_path, summary)

    context = build_package_authority_context(package)
    gate = evaluate_apply_gate(package)

    assert context["canonical_receipt_count"] == 0
    assert context["exact_source_closed"] is False
    assert context["source_authority_verified"] is True
    assert gate["allowed"] is True


def test_bound_canonical_receipt_projects_exact_source_closure(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(tmp_path / "package")

    context = build_package_authority_context(package)

    assert context["canonical_receipt_count"] == 1
    assert context["exact_source_closed"] is True
    assert context["source_authority_verified"] is True
