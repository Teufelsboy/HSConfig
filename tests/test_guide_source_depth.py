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
