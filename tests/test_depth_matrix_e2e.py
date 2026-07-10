import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.io import read_json, write_json


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
MECHPALA_CODE = (
    "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/"
    "AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA=="
)


def test_depth_matrix_shadowpriest_primary_surface_contract(tmp_path: Path):
    out = tmp_path / "shadowpriest"
    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_depth.json",
            "--json",
        ]
    )

    reports = out / "reports"
    deck_dir = out / "CustomConfig" / "shadowpriest"
    operator = read_json(reports / "operator_summary.json")
    gameplan = read_json(reports / "gameplan_contract.json")
    globalvalues_profile = read_json(reports / "globalvalues_profile.json")

    assert code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert operator["guide_strength_summary"]["cards_needing_runtime_surface"] == 0
    assert operator["semantic_blockers"] == []
    assert (deck_dir / "GlobalValues.json").exists()
    assert (deck_dir / "Mulligan.json").exists()
    assert any(path.name.endswith(".json") for path in deck_dir.glob("SW_*.json"))
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    assert gameplan["cards"]["SW_448"]["linked_entities"]
    assert any(
        effect["target_card_id"] == "EX1_625t"
        for effect in gameplan["deckwide_effects"]
    )
    assert globalvalues_profile["keys"]["MyHeroPowerValue"]["status"] == "overlay_changed"


def test_depth_matrix_mechpala_real_contrast_posture(tmp_path: Path):
    fixture = json.loads(
        Path("tests/fixtures/source_documents_multiarchetype.json").read_text(
            encoding="utf-8"
        )
    )
    source_path = tmp_path / "mechpala_sources.json"
    write_json(source_path, fixture["MechPala"])
    out = tmp_path / "mechpala"

    code = main(
        [
            "prepare",
            "--deck-name",
            "MechPala",
            "--deck-code",
            MECHPALA_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(source_path),
            "--json",
        ]
    )

    operator = read_json(out / "reports" / "operator_summary.json")
    authority = read_json(out / "reports" / "global_values_authority_matrix.json")
    allowed = {row["key"] for row in authority["allowed_step1_overlays"]}

    assert code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["guide_strength_summary"]["cards_needing_runtime_surface"] > 0
    assert authority["posture"] == "token_board"
    assert allowed & {
        "GlobalMinionAttack",
        "GlobalMinionHealth",
        "GlobalMinionIntrinsicValue",
    }


def test_depth_matrix_linked_entity_combo_micro_fixture(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [
            {
                "id": "EX1_001",
                "dbf_id": 1,
                "name": "Discover Card",
                "type": "MINION",
                "text": "Discover a spell.",
                "entourage": ["EX1_002"],
            },
            {
                "id": "EX1_002",
                "dbf_id": 2,
                "name": "Option Alpha",
                "type": "SPELL",
                "text": "Deal damage.",
            },
            {
                "id": "EX1_003",
                "dbf_id": 3,
                "name": "Combo A",
                "type": "SPELL",
                "text": "First combo card.",
            },
            {
                "id": "EX1_004",
                "dbf_id": 4,
                "name": "Second combo card.",
                "type": "SPELL",
                "text": "Second combo card.",
            },
        ],
    )
    cards_json = tmp_path / "cards.json"
    write_json(
        cards_json,
        {
            "cards": [
                {
                    "card_id": "EX1_001",
                    "dbf_id": 1,
                    "count": 2,
                    "name": "Discover Card",
                },
                {"card_id": "EX1_003", "dbf_id": 3, "count": 2, "name": "Combo A"},
                {"card_id": "EX1_004", "dbf_id": 4, "count": 2, "name": "Combo B"},
            ]
        },
    )
    source_documents = tmp_path / "source_documents.json"
    write_json(
        source_documents,
        {
            "source_documents": [
                {
                    "source_url": "https://example.invalid/depth-matrix",
                    "source_title": "Depth Matrix Fixture",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-07T00:00:00Z",
                    "claims": [
                        {
                            "claim_kind": "discover_choice",
                            "cards": ["EX1_001"],
                            "option_card_id": "EX1_002",
                            "stance": "pick_option_alpha",
                            "evidence_text_short": "Prefer Option Alpha from this discover pool.",
                            "source_confidence": "high",
                        },
                        {
                            "claim_kind": "combo_sequence",
                            "cards": ["EX1_003", "EX1_004"],
                            "sequence": ["EX1_003", "EX1_004"],
                            "timing_kind": "same_turn",
                            "operator": ">>",
                            "values": ["8", "14"],
                            "evidence_text_short": "Play Combo A into Combo B on the same turn.",
                            "source_confidence": "high",
                        },
                    ],
                }
            ]
        },
    )
    out = tmp_path / "linked_combo"

    code = main(
        [
            "prepare",
            "--deck-name",
            "Linked Combo",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    deck_dir = out / "CustomConfig" / "linked_combo"
    reports = out / "reports"
    combo = read_json(deck_dir / "Combo.json")
    card_behavior = read_json(reports / "card_behavior_plan_report.json")
    suppression = read_json(reports / "card_behavior_suppression_report.json")
    discover = read_json(deck_dir / "EX1_001.json")

    assert code == 0
    assert combo["ComboList"]["values"][0]["combo"] == "EX1_003>>EX1_004"
    assert combo["ComboList"]["values"][0]["value"] == "8>>14"
    assert card_behavior["option_resolution"][0]["status"] == "resolved"
    assert suppression == [
        {
            "claim_id": suppression[0]["claim_id"],
            "claim_kind": "mechanic_usage",
            "cards": ["EX1_001"],
            "reason": "covered_by_resolved_choice_surface",
        }
    ]
    assert "OnDiscoverCardBonus" in discover
    assert "source_claim_ids" not in json.dumps(discover)
