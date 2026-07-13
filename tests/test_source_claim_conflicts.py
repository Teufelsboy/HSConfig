from hsconfig.source_claim_conflicts import build_claim_conflict_report


def _claim(claim_id, claim_kind, card, **extra):
    return {
        "claim_id": claim_id,
        "claim_kind": claim_kind,
        "cards": [card],
        "claim_readiness": "guide_backed",
        "source_confidence": "high",
        "evidence_text_short": claim_id,
        **extra,
    }


def test_conflict_report_keeps_existing_mulligan_conflict_shape():
    report = build_claim_conflict_report(
        [
            _claim("keep", "mulligan_keep", "CARD_001"),
            _claim("discard", "mulligan_discard", "CARD_001"),
        ]
    )

    assert report["conflict_count"] == 1
    conflict = report["conflicts"][0]
    assert conflict["conflict_family"] == "mulligan"
    assert conflict["card_id"] == "CARD_001"
    assert conflict["resolution"] == "downgrade_to_report_visible_conflict"


def test_conflict_report_detects_targeting_scope_conflicts():
    report = build_claim_conflict_report(
        [
            _claim(
                "face",
                "targeting_rule",
                "BURN",
                semantic_qualifiers={"target_scope": "enemy_hero"},
            ),
            _claim(
                "minion",
                "targeting_rule",
                "BURN",
                semantic_qualifiers={"target_scope": "enemy_minion"},
            ),
        ]
    )

    assert report["conflict_count"] == 1
    assert report["conflicts"][0]["conflict_family"] == "targeting"
    assert set(report["conflicts"][0]["values"]) == {"enemy_hero", "enemy_minion"}


def test_conflict_report_detects_combo_timing_conflicts():
    report = build_claim_conflict_report(
        [
            _claim("same_turn", "combo_sequence", "A", sequence=["A", "B"], timing_kind="same_turn"),
            _claim("cross_turn", "combo_sequence", "A", sequence=["A", "B"], timing_kind="cross_turn"),
        ]
    )

    assert report["conflict_count"] == 1
    assert report["conflicts"][0]["conflict_family"] == "combo_timing"


def test_conflict_report_detects_option_choice_conflicts():
    report = build_claim_conflict_report(
        [
            _claim("option_a", "discover_choice", "DISCOVER", option_card_id="OPTION_A"),
            _claim("option_b", "discover_choice", "DISCOVER", option_card_id="OPTION_B"),
        ]
    )

    assert report["conflict_count"] == 1
    assert report["conflicts"][0]["conflict_family"] == "option_choice"
