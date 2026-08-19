from hsconfig.output_ownership_manifest import build_output_ownership_manifest


def test_pre_run_reports_are_diagnostic_and_operator_summary_is_the_only_gate():
    paths = [
        "reports/operator_summary.json",
        "reports/layered_evidence_contract.json",
        "reports/source_acquisition_closure.json",
        "reports/disposition_ledger.json",
        "reports/globalvalues_decision_ledger.json",
        "reports/pre_run_closure.json",
    ]

    manifest = build_output_ownership_manifest(paths)
    by_file = {row["file"]: row for row in manifest["files"]}

    for path in paths[1:]:
        assert by_file[path]["classification"] == "diagnostic"
        assert by_file[path]["diagnostic_only"] is True
        assert by_file[path]["can_block_apply"] is False
        assert by_file[path]["authority"].startswith("diagnostic_pre_run_")
    assert [
        row["file"]
        for row in manifest["files"]
        if row["classification"] == "gate"
    ] == ["reports/operator_summary.json"]


def test_unknown_custom_config_json_names_are_unclassified_not_cardid_surfaces():
    paths = (
        "CustomConfig/deck/FutureOptionalSurface.json",
        "CustomConfig/deck/notes.json",
    )

    manifest = build_output_ownership_manifest(paths)
    by_file = {row["file"]: row for row in manifest["files"]}

    for path in paths:
        assert by_file[path]["classification"] == "unclassified"
        assert by_file[path]["runtime_surface"] is None
    assert manifest["summary"]["unclassified_file_count"] == 2
    assert manifest["summary"]["runtime_surface_count"] == 0


def test_historical_synthetic_cardid_name_remains_diagnostic_only():
    path = "CustomConfig/discover_deck/DISCOVER_CARD.json"

    manifest = build_output_ownership_manifest([path])
    row = manifest["files"][0]

    assert row["classification"] == "diagnostic"
    assert row["runtime_surface"] is None
    assert row["diagnostic_only"] is True
    assert manifest["summary"]["unclassified_file_count"] == 0
    assert manifest["summary"]["runtime_surface_count"] == 0


def test_package_derivation_receipt_is_integrity_authority_not_second_human_gate():
    manifest = build_output_ownership_manifest(
        [
            "package_derivation_receipt.json",
            "reports/operator_summary.json",
        ]
    )

    by_file = {row["file"]: row for row in manifest["files"]}

    assert by_file["package_derivation_receipt.json"] == {
        "file": "package_derivation_receipt.json",
        "producer": "prepare",
        "classification": "integrity_receipt",
        "authority": "package_derivation_receipt",
        "can_block_apply": True,
        "runtime_surface": None,
        "diagnostic_only": False,
    }
    assert [
        row["file"] for row in manifest["files"] if row["classification"] == "gate"
    ] == ["reports/operator_summary.json"]


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


def test_linked_runtime_entity_has_explicit_source_to_owner_manifest_row():
    manifest = build_output_ownership_manifest(
        [
            "CustomConfig/shadowpriest/SW_448.json",
            "CustomConfig/shadowpriest/EX1_625t.json",
        ],
        card_behavior_plan={
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )

    assert manifest["runtime_entity_ownership"] == [
        {
            "path": "CardID/EX1_625t.json",
            "owner_kind": "linked_runtime_entity",
            "source_card_id": "SW_448",
            "runtime_card_id": "EX1_625t",
            "link_kind": "hero_power_transform",
        }
    ]
    by_file = {row["file"]: row for row in manifest["files"]}
    assert by_file["CustomConfig/shadowpriest/EX1_625t.json"]["owner_kind"] == (
        "linked_runtime_entity"
    )
    assert by_file["CustomConfig/shadowpriest/EX1_625t.json"]["source_card_id"] == (
        "SW_448"
    )
    assert "owner_kind" not in by_file["CustomConfig/shadowpriest/SW_448.json"]


def test_optimized_report_ownership_is_mode_bound():
    optimized_paths = (
        "reports/optimized_start/starter_context.json",
        "reports/optimized_start/candidate-1.json",
        "reports/optimized_start/candidate-2.json",
        "reports/optimized_start/candidate-3.json",
        "reports/optimized_start/starter_config_decision.json",
    )

    manifest = build_output_ownership_manifest(
        ["reports/operator_summary.json", *optimized_paths]
    )
    by_file = {row["file"]: row for row in manifest["files"]}

    for path in optimized_paths:
        assert by_file[path]["classification"] == "diagnostic"
        assert by_file[path]["authority"] == "diagnostic_optimized_start"
        assert by_file[path]["configuration_modes"] == [
            "LLM_OPTIMIZED_START"
        ]
        assert by_file[path]["diagnostic_only"] is True
        assert by_file[path]["can_block_apply"] is False
    assert manifest["summary"]["unclassified_file_count"] == 0
    assert [
        row["file"]
        for row in manifest["files"]
        if row["classification"] == "gate"
    ] == ["reports/operator_summary.json"]
