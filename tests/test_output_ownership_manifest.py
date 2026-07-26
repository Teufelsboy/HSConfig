from hsconfig.output_ownership_manifest import build_output_ownership_manifest


def test_surface_intent_shape_change_stays_diagnostic_without_second_apply_authority():
    manifest = build_output_ownership_manifest(
        [
            "reports/operator_summary.json",
            "reports/surface_intent.json",
        ]
    )

    by_file = {row["file"]: row for row in manifest["files"]}

    assert by_file["reports/surface_intent.json"] == {
        "file": "reports/surface_intent.json",
        "producer": "prepare",
        "classification": "diagnostic",
        "authority": "diagnostic_artifact",
        "can_block_apply": False,
        "runtime_surface": None,
        "diagnostic_only": True,
    }
    assert [
        row["file"] for row in manifest["files"] if row["classification"] == "gate"
    ] == ["reports/operator_summary.json"]


def test_source_bundle_is_a_diagnostic_artifact_not_an_apply_authority():
    manifest = build_output_ownership_manifest(
        ["reports/operator_summary.json", "reports/source_bundle.json"]
    )

    by_file = {row["file"]: row for row in manifest["files"]}

    assert by_file["reports/source_bundle.json"]["classification"] == "diagnostic"
    assert by_file["reports/source_bundle.json"]["diagnostic_only"] is True
    assert by_file["reports/source_bundle.json"]["can_block_apply"] is False


def test_source_closure_intake_receipt_is_diagnostic_not_an_apply_authority():
    manifest = build_output_ownership_manifest(
        [
            "reports/operator_summary.json",
            "reports/02_source_acquisition/source_closure_intake_receipt.json",
        ]
    )

    by_file = {row["file"]: row for row in manifest["files"]}
    receipt = by_file[
        "reports/02_source_acquisition/source_closure_intake_receipt.json"
    ]

    assert receipt["classification"] == "diagnostic"
    assert receipt["authority"] == "diagnostic_source_closure_intake"
    assert receipt["diagnostic_only"] is True
    assert receipt["can_block_apply"] is False


def test_source_evidence_closure_is_a_diagnostic_artifact_not_an_apply_authority():
    manifest = build_output_ownership_manifest(
        ["reports/operator_summary.json", "reports/source_evidence_closure.json"]
    )

    by_file = {row["file"]: row for row in manifest["files"]}

    assert by_file["reports/source_evidence_closure.json"]["classification"] == (
        "diagnostic"
    )
    assert by_file["reports/source_evidence_closure.json"]["authority"] == (
        "diagnostic_source_evidence_closure"
    )
    assert by_file["reports/source_evidence_closure.json"]["diagnostic_only"] is True
    assert by_file["reports/source_evidence_closure.json"]["can_block_apply"] is False


def test_plan_input_diagnostics_is_classified_without_a_second_apply_authority():
    manifest = build_output_ownership_manifest(
        ["reports/operator_summary.json", "reports/plan_input_diagnostics.json"]
    )

    by_file = {row["file"]: row for row in manifest["files"]}
    diagnostics = by_file["reports/plan_input_diagnostics.json"]

    assert diagnostics["classification"] == "diagnostic"
    assert diagnostics["authority"] == "diagnostic_artifact"
    assert diagnostics["diagnostic_only"] is True
    assert diagnostics["can_block_apply"] is False
    assert manifest["summary"]["unclassified_file_count"] == 0
