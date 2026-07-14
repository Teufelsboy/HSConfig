import json
from pathlib import Path

from hsconfig.cli import main
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


def test_conflict_report_detects_role_against_known_bad_pattern():
    report = build_claim_conflict_report(
        [
            _claim(
                "use_enemy_minion",
                "card_role",
                "TARGETER",
                stance="prefer_enemy_minion",
            ),
            _claim(
                "do_not_target_enemy_minion",
                "known_bad_pattern",
                "TARGETER",
                stance="do_not_target_enemy_minion",
            ),
        ]
    )

    assert report["conflict_count"] == 1
    conflict = report["conflicts"][0]
    assert conflict["card_id"] == "TARGETER"
    assert conflict["conflict_family"] == "role_vs_known_bad_pattern"
    assert conflict["values"] == ["enemy_minion->do_not_target_enemy_minion"]
    assert conflict["claim_ids"] == ["do_not_target_enemy_minion", "use_enemy_minion"]
    assert conflict["resolution"] == "downgrade_to_report_visible_conflict"


def test_package_keeps_conflicted_mulligan_claims_visible_but_not_lowered(tmp_path: Path):
    out = tmp_path / "pkg"
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_001",
                        "dbf_id": 1,
                        "count": 1,
                        "name": "Conflict Card",
                        "cost": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    guide_sources_json = tmp_path / "guide_sources.json"
    guide_sources_json.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.invalid/conflict",
                    "source_title": "Conflict Fixture",
                    "source_family": "guide_fixture",
                    "retrieved_at": "2026-07-13T00:00:00Z",
                    "claims": [
                        {
                            "claim_id": "keep_card",
                            "claim_kind": "mulligan_keep",
                            "cards": ["CARD_001"],
                            "evidence_text_short": "keep conflict card",
                            "source_confidence": "guide_backed",
                        },
                        {
                            "claim_id": "discard_card",
                            "claim_kind": "mulligan_discard",
                            "cards": ["CARD_001"],
                            "evidence_text_short": "discard conflict card",
                            "source_confidence": "guide_backed",
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "prepare",
            "--deck-name",
            "ConflictDeck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--guide-sources-json",
            str(guide_sources_json),
        ]
    )

    deck_dir = next((out / "CustomConfig").iterdir())
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    audit = json.loads(
        (out / "reports" / "source_contract_audit.json").read_text(encoding="utf-8")
    )
    conflict_report = json.loads(
        (out / "reports" / "claim_conflict_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert conflict_report["conflict_count"] == 1
    conflict_claim_ids = set(conflict_report["conflicts"][0]["claim_ids"])
    assert len(conflict_claim_ids) == 2
    assert conflict_claim_ids <= set(audit["claim_rows"])
    assert all(
        row["builder_or_router_decision"] != "emitted"
        for row in audit["claim_lifecycle_rows"]
        if row["claim_id"] in conflict_claim_ids
    )
    assert not any(
        row.get("mulligan") == "CARD_001" for row in mulligan["Mulligan"]["values"]
    )
