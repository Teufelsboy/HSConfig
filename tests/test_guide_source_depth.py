from hsconfig.guide_source_depth import build_guide_source_depth_report


def test_depth_report_counts_card_lanes_and_source_families():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "claim_keep",
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_001"],
                    "source_family": "guide",
                },
                {
                    "claim_id": "claim_target",
                    "claim_kind": "targeting_rule",
                    "cards": ["CARD_001"],
                    "source_family": "guide",
                },
            ],
            "unsupported_claims": [],
            "source_evidence_index": [
                {"source_ref": "source:1", "source_family": "guide", "claim_count": 2}
            ],
        },
        config_readiness_report={
            "summary": {"total_cards": 1, "runtime_emitted": 1, "generic_low_confidence": 0},
            "cards": {
                "CARD_001": {
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                    "source_claim_ids": ["claim_keep", "claim_target"],
                }
            },
        },
    )

    assert report["summary"]["claim_count"] == 2
    assert report["summary"]["unsupported_claim_count"] == 0
    assert report["summary"]["total_cards"] == 1
    assert report["summary"]["supported_cards"] == 1
    assert report["summary"]["cards_needing_guide_claims"] == 0
    assert report["summary"]["warnings_count"] == 0
    assert report["source_families"] == {"guide": 2}
    assert report["claim_kinds"] == {"mulligan_keep": 1, "targeting_rule": 1}
    assert report["warnings"] == []
    assert report["depth_status"] == "usable"


def test_depth_report_warns_when_cards_need_guide_claims():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [],
            "unsupported_claims": [],
            "source_evidence_index": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 1, "runtime_emitted": 0, "generic_low_confidence": 1},
            "cards": {
                "CARD_002": {
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                    "source_claim_ids": [],
                }
            },
        },
    )

    assert report["depth_status"] == "needs_more_research"
    assert report["summary"]["claim_count"] == 0
    assert report["summary"]["unsupported_claim_count"] == 0
    assert report["summary"]["total_cards"] == 1
    assert report["summary"]["supported_cards"] == 0
    assert report["summary"]["cards_needing_guide_claims"] == 1
    assert report["summary"]["warnings_count"] == 1
    assert report["source_families"] == {}
    assert report["claim_kinds"] == {}
    assert report["warnings"] == [
        {
            "card_id": "CARD_002",
            "reason": "needs_guide_claim",
            "readiness_lane": "generic_low_confidence",
        }
    ]


def test_depth_report_marks_usable_with_runtime_gaps():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "claim_role",
                    "claim_kind": "card_role",
                    "cards": ["EX1_READY"],
                    "source_family": "guide",
                }
            ],
            "unsupported_claims": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 2},
            "cards": {
                "EX1_READY": {
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                },
                "EX1_GAP": {
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                },
            },
        },
    )

    assert report["depth_status"] == "usable_with_runtime_gaps"
    assert report["summary"]["cards_needing_runtime_surface"] == 1


def test_depth_report_guide_gap_takes_precedence_over_runtime_gap():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "claim_role",
                    "claim_kind": "card_role",
                    "cards": ["EX1_RUNTIME_GAP"],
                    "source_family": "guide",
                }
            ],
            "unsupported_claims": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 2},
            "cards": {
                "EX1_RUNTIME_GAP": {
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                },
                "EX1_GUIDE_GAP": {
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                },
            },
        },
    )

    assert report["depth_status"] == "needs_more_research"
    assert report["summary"]["cards_needing_runtime_surface"] == 1
    assert report["summary"]["cards_needing_guide_claims"] == 1


def test_depth_report_surfaces_claim_conflicts_and_low_confidence_coverage():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [],
            "unsupported_claims": [],
            "source_evidence_index": [],
            "claim_conflict_report": {
                "conflict_count": 1,
                "conflicts": [{"card_id": "CARD_001"}],
            },
            "claim_coverage_report": {
                "summary": {
                    "guide_backed": 1,
                    "static_semantics_backfilled": 0,
                    "uncovered_low_confidence": 2,
                }
            },
        },
        config_readiness_report={
            "summary": {"total_cards": 2},
            "cards": {},
        },
    )

    assert {"reason": "claim_conflicts_present", "conflict_count": 1} in report["warnings"]
    assert {"reason": "cards_still_low_confidence", "card_count": 2} in report["warnings"]
    assert report["summary"]["warnings_count"] == 2


def test_depth_report_separates_lowerable_and_report_only_claims():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_id": "claim_good",
                    "claim_kind": "targeting_rule",
                    "source_family": "guide",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "guide",
                    "cards": ["CARD_A"],
                },
                {
                    "claim_id": "claim_low",
                    "claim_kind": "card_role",
                    "source_family": "guide",
                    "claim_readiness": "explicit_low_confidence",
                    "trust_ceiling": "report_only",
                    "cards": ["CARD_B"],
                },
            ],
            "unsupported_claims": [],
            "claim_coverage_report": {
                "total_cards": 2,
                "cards": {
                    "CARD_A": {"coverage_status": "guide_backed"},
                    "CARD_B": {"coverage_status": "uncovered_low_confidence"},
                },
                "summary": {
                    "guide_backed": 1,
                    "static_semantics_backfilled": 0,
                    "uncovered_low_confidence": 1,
                },
            },
        },
        config_readiness_report={
            "summary": {
                "cards_needing_guide_claims": 1,
            }
        },
    )

    assert report["summary"]["lowerable_claims"] == 1
    assert report["summary"]["report_only_claims"] == 1


def test_report_only_claims_do_not_produce_source_backed_depth():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "claim_readiness": "explicit_low_confidence",
                    "trust_ceiling": "report_only",
                    "source_family": "guide",
                }
            ],
            "unsupported_claims": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 1, "runtime_emitted": 0, "generic_low_confidence": 1},
            "cards": {
                "CARD_A": {
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                }
            },
        },
    )

    assert report["summary"]["lowerable_claims"] == 0
    assert report["summary"]["report_only_claims"] == 1
    assert report["source_depth_status"] == "needs_more_research"


def test_static_semantics_claims_do_not_produce_source_backed_depth():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_kind": "mechanic_usage",
                    "claim_readiness": "source_backed_static_semantics",
                    "trust_ceiling": "static_semantics",
                    "cards": ["CARD_STATIC"],
                    "source_family": "hearthstonejson_static_semantics",
                }
            ],
            "unsupported_claims": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 1, "runtime_emitted": 1, "generic_low_confidence": 0},
            "cards": {
                "CARD_STATIC": {
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                }
            },
        },
    )

    assert report["summary"]["claim_count"] == 1
    assert report["summary"]["lowerable_claims"] == 1
    assert report["summary"]["strong_lowerable_claims"] == 0
    assert report["depth_status"] == "usable"
    assert report["source_depth_status"] == "static_semantics_only"


def test_diagnostic_static_report_only_claims_do_not_block_source_backed_depth():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "guide",
                    "cards": ["CARD_GUIDE"],
                    "source_family": "guide",
                },
                {
                    "claim_kind": "mechanic_usage",
                    "claim_readiness": "source_backed_static_semantics",
                    "trust_ceiling": "report_only",
                    "cards": ["CARD_STATIC"],
                    "source_family": "hearthstonejson_static_semantics",
                },
            ],
            "unsupported_claims": [],
        },
        config_readiness_report={
            "summary": {"total_cards": 2, "runtime_emitted": 2, "generic_low_confidence": 0},
            "cards": {
                "CARD_GUIDE": {
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                },
                "CARD_STATIC": {
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                },
            },
        },
    )

    assert report["summary"]["strong_lowerable_claims"] == 1
    assert report["summary"]["report_only_claims"] == 0
    assert report["summary"]["diagnostic_report_only_claims"] == 1
    assert report["source_depth_status"] == "source_backed"


def test_guide_source_depth_separates_strong_lowerable_from_report_only():
    report = build_guide_source_depth_report(
        guide_claim_bundle={
            "claims": [
                {
                    "claim_kind": "card_role",
                    "claim_readiness": "guide_backed",
                    "trust_ceiling": "guide",
                    "cards": ["CARD_A"],
                    "source_family": "guide",
                },
                {
                    "claim_kind": "card_role",
                    "claim_readiness": "explicit_low_confidence",
                    "trust_ceiling": "report_only",
                    "cards": ["CARD_B"],
                    "source_family": "guide",
                },
            ],
            "unsupported_claims": [],
            "claim_coverage_report": {"cards": {}},
        },
        config_readiness_report={
            "summary": {"total_cards": 2},
            "cards": {
                "CARD_A": {"readiness_lane": "runtime_emitted", "first_missing_link": "none"},
                "CARD_B": {"readiness_lane": "generic_low_confidence", "first_missing_link": "needs_guide_claim"},
            },
        },
    )

    assert report["summary"]["strong_lowerable_claims"] == 1
    assert report["summary"]["report_only_claims"] == 1
    assert report["summary"]["blocked_runtime_claims"] == 1
    assert report["source_depth_status"] == "needs_more_research"
