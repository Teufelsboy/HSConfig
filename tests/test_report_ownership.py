from hsconfig.report_ownership import build_report_ownership


def test_report_ownership_covers_operator_reports():
    rows = build_report_ownership()
    by_file = {row["file"]: row for row in rows}

    assert by_file["reports/operator_summary.json"]["authority"] == "normal_operator_gate"
    assert by_file["reports/source_claim_gap_report.json"]["answers"] == "which card link is missing first"
    assert by_file["reports/strong_promotion_report.json"]["answers"] == "whether the package can be called source-backed strong"
    assert by_file["reports/per_card_config_readiness_report.json"]["answers"] == "which lane each card occupies"
    assert by_file["reports/guide_source_depth_report.json"]["answers"] == "how strong the guide and source coverage is"
    assert by_file["reports/global_values_authority_matrix.json"]["answers"] == "which GlobalValues keys are source-backed or archetype-inferred"


def test_report_ownership_has_single_open_first_report():
    rows = build_report_ownership()

    open_first = [row for row in rows if row["open_order"] == "1"]

    assert [row["file"] for row in open_first] == ["reports/operator_summary.json"]


def test_operator_summary_owns_config_usefulness_signal():
    ownership = build_report_ownership()
    operator = next(row for row in ownership if row["file"] == "reports/operator_summary.json")

    assert "config_usefulness" in operator["contains"]
    assert operator["authority"] == "normal_operator_gate"
