import json
import tomllib
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_validate_missing_package_returns_nonzero_json(tmp_path: Path, capsys):
    code = main(["validate", "--package", str(tmp_path / "missing"), "--json"])

    captured = capsys.readouterr()

    assert code == 1
    assert json.loads(captured.out)["status"] == "failed"


def test_pyproject_exposes_hsconfig_entrypoint():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["hsconfig"] == "hsconfig.cli:main"


def test_build_accepts_cards_json_object(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Card One"},
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 1, "name": "Card Two"},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Explicit Cards",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert payload["status"] == "passed"
    assert (out / "CustomConfig" / "explicit_cards" / "EX1_001.json").exists()
    assert (out / "CustomConfig" / "explicit_cards" / "EX1_002.json").exists()


def test_build_decodes_deck_code_by_default(tmp_path: Path, capsys):
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    reports = out / "reports"
    deck_identity = json.loads((reports / "deck_identity.json").read_text(encoding="utf-8"))
    manifest = json.loads((reports / "input_manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((reports / "deckstring_decode_receipt.json").read_text(encoding="utf-8"))
    card_id_map = json.loads((reports / "card_id_map.json").read_text(encoding="utf-8"))
    semantic_report = json.loads(
        (reports / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert deck_identity["hero_dbf_id"] == 813
    assert deck_identity["format"] == "FT_WILD"
    assert deck_identity["card_count_total"] == 30
    assert manifest["card_source"] == "deckstring"
    assert manifest["format"] == "FT_WILD"
    assert receipt["decoder"] == "hearthstone.deckstrings"
    assert card_id_map["545"]["card_id"] == "DS1_233"
    assert any(card["card_id"] == "SW_448" for card in semantic_report["cards"])
    assert (reports / "card_semantic_audit.md").exists()
    assert (out / "CustomConfig" / "shadowpriest" / "DS1_233.json").exists()


def test_build_rejects_invalid_deck_code_without_placeholder_flag(tmp_path: Path, capsys):
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Fixture Deck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 1
    assert payload["status"] == "failed"
    assert not list(out.glob("CustomConfig/fixture_deck/HSC_*.json"))


def test_build_accepts_claims_json_for_guide_backed_config(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "EX1_001",
                        "dbf_id": 1,
                        "count": 2,
                        "name": "Pressure One",
                        "text": "Battlecry: deal damage.",
                    },
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 1, "name": "Burst Two"},
                ]
            }
        ),
        encoding="utf-8",
    )
    claims_json = tmp_path / "claims.json"
    claims_json.write_text(
        json.dumps(
            [
                {
                    "source": "guide",
                    "url": "https://example.invalid/deck-guide",
                    "claim": "Always keep Pressure One and push face damage early.",
                    "cards": ["EX1_001"],
                    "claim_type": "mulligan_and_gameplan",
                },
                {
                    "source": "guide",
                    "url": "https://example.invalid/deck-guide",
                    "claim": "Use Pressure One with Burst Two for a combo burst turn.",
                    "cards": ["EX1_001", "EX1_002"],
                    "claim_type": "combo",
                    "values": ["8", "14"],
                },
            ]
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Guide Cards",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--claims-json",
            str(claims_json),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    deck_dir = out / "CustomConfig" / "guide_cards"
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    combo = json.loads((deck_dir / "Combo.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert mulligan["Mulligan"]["values"][0]["mulligan"] == "EX1_001"
    assert combo["ComboList"]["values"][0]["combo"] == "EX1_001 >> EX1_002"
