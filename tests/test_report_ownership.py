from hsconfig.report_ownership import build_report_ownership


def test_report_ownership_covers_operator_reports():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    assert by_file["reports/operator_summary.json"]["authority"] == "normal_operator_gate"
    assert by_file["reports/source_to_runtime_explainability.json"]["answers"] == (
        "which exact source-to-runtime link is missing before a card can be stronger"
    )
    assert by_file["reports/source_evidence_closure.json"]["answers"] == (
        "compact source evidence closure summary for generated package quality"
    )
    assert by_file["reports/source_contract_audit.json"]["answers"] == (
        "why each source claim did or did not lower to runtime config"
    )
    assert by_file["reports/source_claim_gap_report.json"]["answers"] == "which card link is missing first"
    assert by_file["reports/strong_promotion_report.json"]["answers"] == "whether the package can be called source-backed strong"
    assert by_file["reports/per_card_config_readiness_report.json"]["answers"] == "which lane each card occupies"
    assert by_file["reports/guide_source_depth_report.json"]["answers"] == "how strong the guide and source coverage is"
    assert by_file["reports/global_values_authority_matrix.json"]["answers"] == "which GlobalValues keys are source-backed or archetype-inferred"
    assert by_file["reports/output_ownership_manifest.json"]["authority"] == (
        "diagnostic_artifact_ownership"
    )
    assert by_file["reports/output_ownership_manifest.json"]["classification"] == "diagnostic"


def test_report_ownership_has_single_open_first_report():
    rows = build_report_ownership()

    open_first = [row for row in rows if row["open_order"] == "1"]

    assert [row["file"] for row in open_first] == ["reports/operator_summary.json"]


def test_operator_summary_owns_config_usefulness_signal():
    ownership = build_report_ownership()
    operator = next(row for row in ownership if row["file"] == "reports/operator_summary.json")

    assert "config_usefulness" in operator["contains"]
    assert operator["authority"] == "normal_operator_gate"


def test_report_ownership_includes_mechanic_diagnostics():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    assert by_file["reports/mechanic_drift_report.json"]["authority"] == "non_blocking_mechanic_drift_visibility"
    assert by_file["reports/mechanic_drift_report.json"]["open_order"] == "9"
    assert by_file["reports/semantic_enrichment_report.json"]["authority"] == "semantic_mechanic_diagnostics"
    assert by_file["reports/semantic_enrichment_report.json"]["open_order"] == "10"


def test_source_contract_audit_is_diagnostic_not_gate():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    audit = by_file["reports/source_contract_audit.json"]

    assert audit["authority"] == "diagnostic_source_to_runtime_explanation"
    assert audit["open_order"] != "1"
    assert "does not grant apply permission" in audit["notes"]


def test_source_to_runtime_explainability_is_diagnostic_not_gate():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    explainability = by_file["reports/source_to_runtime_explainability.json"]

    assert explainability["authority"] == "diagnostic_source_to_runtime_projection"
    assert explainability["open_order"] == "2"
    assert "does not grant apply permission" in explainability["notes"]


def test_source_evidence_closure_is_diagnostic_not_gate():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    closure = by_file["reports/source_evidence_closure.json"]

    assert closure["authority"] == "diagnostic_source_evidence_closure"
    assert closure["classification"] == "diagnostic"
    assert closure["open_order"] == "2.5"
    assert "does not grant apply permission" in closure["notes"]


def test_source_contract_conformance_is_not_operator_report():
    ownership = build_report_ownership()
    files = {row["file"] for row in ownership}

    assert "reports/source_contract_conformance.json" not in files
    assert "reports/operator_summary.json" in files
    assert "reports/source_contract_audit.json" in files


def test_report_ownership_classifies_every_operator_report_and_keeps_single_gate():
    rows = build_report_ownership()

    assert rows
    assert all(row.get("classification") for row in rows)
    gates = [row for row in rows if row["classification"] == "gate"]
    assert [row["file"] for row in gates] == ["reports/operator_summary.json"]
    assert all(
        row["classification"] != "gate" or row["authority"] == "normal_operator_gate"
        for row in rows
    )
