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
