import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_shadowpriest_guide_depth_package_has_real_plans_and_clean_runtime(tmp_path: Path, capsys):
    cards_json = tmp_path / "shadow_cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "SW_448",
                        "dbf_id": 1,
                        "count": 1,
                        "name": "Darkbishop Benedictus",
                        "text": "At the start of the game, if the spells in your deck are all Shadow, enter Shadowform.",
                    },
                    {
                        "card_id": "BAR_311",
                        "dbf_id": 2,
                        "count": 2,
                        "name": "Frazzled Freshman",
                        "text": "A strong early minion.",
                    },
                    {
                        "card_id": "SW_446",
                        "dbf_id": 3,
                        "count": 1,
                        "name": "Mind Spike",
                        "text": "Hero Power: Deal 2 damage.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--guide-sources-json",
            "tests/fixtures/shadowpriest_guide_sources.json",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    reports = package / "reports"
    deck_dir = package / "CustomConfig" / "shadowpriest"
    guide_claims = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    cardid = json.loads((deck_dir / "SW_446.json").read_text(encoding="utf-8"))
    behavior_report = json.loads((reports / "card_behavior_plan_report.json").read_text(encoding="utf-8"))
    mulligan_report = json.loads((reports / "mulligan_plan_report.json").read_text(encoding="utf-8"))
    global_authority = json.loads(
        (reports / "global_values_authority_matrix.json").read_text(encoding="utf-8")
    )

    mulligan_values = mulligan["Mulligan"]["values"]

    assert code == 0
    assert payload["status"] == "passed"
    assert guide_claims["claims"]
    assert [row["mulligan"] for row in mulligan_values[:2]] == ["SW_448", "BAR_311"]
    assert mulligan_values[-1]["mulligan"] == "*"
    assert all(set(row) == {"comment", "mulligan", "condition", "value"} for row in mulligan_values)
    assert "BeforePlayCardBonus" in cardid
    assert all("source_claim_ids" not in row for block in cardid.values() if isinstance(block, dict) for row in block.get("values", []))
    assert behavior_report["card_rows"]["SW_446"][0]["intent"] == "prefer_enemy_hero"
    assert mulligan_report["quality"]["has_concrete_keeps"] is True
    assert any(row["key"] == "FirstTurnValueWeight" for row in global_authority["allowed_step1_overlays"])


def test_real_shadowpriest_deckcode_depth_prepare_has_clean_runtime(tmp_path: Path, capsys):
    guide_sources = tmp_path / "real_shadow_sources.json"
    guide_sources.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.invalid/shadow-priest-real",
                    "source_title": "Shadow Priest Fixture",
                    "source_family": "guide_fixture",
                    "claims": [
                        {
                            "claim_kind": "mulligan_keep",
                            "cards": ["SW_448"],
                            "stance": "keep",
                            "evidence_text_short": "Keep Darkbishop Benedictus to enable the hero power plan.",
                            "source_confidence": "high",
                        },
                        {
                            "claim_kind": "gameplan_posture",
                            "scope": "deck",
                            "stance": "aggressive",
                            "evidence_text_short": "Shadow Priest is an aggressive pressure deck.",
                            "source_confidence": "medium",
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

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
            str(package),
            "--guide-sources-json",
            str(guide_sources),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    reports = package / "reports"
    deck_identity = json.loads((reports / "deck_identity.json").read_text(encoding="utf-8"))
    validation = json.loads((reports / "validation_report.json").read_text(encoding="utf-8"))
    guide_claims = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    deck_dir = package / "CustomConfig" / "shadowpriest"

    assert code == 0
    assert payload["status"] == "passed"
    assert deck_identity["card_count_total"] == 30
    assert validation["status"] == "passed"
    assert any(claim["claim_kind"] == "gameplan_posture" and claim["scope"] == "deck" for claim in guide_claims["claims"])
    assert (deck_dir / "SW_448.json").exists()
    deck_card_ids = {card["card_id"] for card in deck_identity["cards"]}
    for path in deck_dir.glob("*.json"):
        if path.name not in {"GlobalValues.json", "Mulligan.json", "Combo.json"}:
            assert path.stem in deck_card_ids
    for path in deck_dir.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for block in payload.values():
            if isinstance(block, dict):
                for row in block.get("values", []):
                    assert "source_claim_ids" not in row
                    assert "confidence" not in row
