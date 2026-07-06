import json
import tomllib
from pathlib import Path

from hsconfig.cli import _guide_documents_from_legacy_claims, main


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


def test_readme_documents_prepare_as_normal_path():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "hsconfig prepare" in text
    assert "reports/research" in text
    assert "hsconfig build" in text
    assert "hsconfig apply" in text


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


def test_legacy_claims_synthesize_legacy_retrieved_at_when_unstamped():
    documents = _guide_documents_from_legacy_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/deck-guide",
                "claim": "Always keep Pressure One.",
                "cards": ["EX1_001"],
                "claim_type": "mulligan",
            }
        ]
    )

    assert documents[0]["retrieved_at"] == "1970-01-01T00:00:00Z"


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
    research_dir = out / "reports" / "research"
    archetype_research = json.loads(
        (research_dir / "archetype_research.json").read_text(encoding="utf-8")
    )
    card_role_map = json.loads((research_dir / "card_role_map.json").read_text(encoding="utf-8"))
    mulligan_anchor_map = json.loads(
        (research_dir / "mulligan_anchor_map.json").read_text(encoding="utf-8")
    )
    globalvalue_intent = json.loads(
        (research_dir / "globalvalue_intent.json").read_text(encoding="utf-8")
    )
    deck_dir = out / "CustomConfig" / "guide_cards"
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    combo = json.loads((deck_dir / "Combo.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert archetype_research["confidence"] == "guide_backed"
    assert card_role_map["EX1_001"]["confidence"] == "guide_backed"
    assert mulligan_anchor_map["EX1_001"]["intent"] == "hold"
    assert globalvalue_intent["pressure_bias"] == "high"
    assert mulligan["Mulligan"]["values"][0]["mulligan"] == "EX1_001"
    assert combo["ComboList"]["values"][0]["combo"] == "EX1_001>>EX1_002"


def test_build_consumes_plan_reports_dir_overrides(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Pressure One"},
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 1, "name": "Burst Two"},
                ]
            }
        ),
        encoding="utf-8",
    )
    guide_sources = tmp_path / "sources.json"
    guide_sources.write_text(
        json.dumps(
            [
                {
                    "source_url": "https://example.invalid/guide",
                    "source_title": "Guide",
                    "source_family": "guide",
                    "claims": [
                        {
                            "claim_kind": "mulligan_keep",
                            "cards": ["EX1_001"],
                            "stance": "keep",
                            "evidence_text_short": "Keep Pressure One.",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    plan_reports = tmp_path / "plan_reports"
    plan_reports.mkdir()
    (plan_reports / "mulligan_plan_report.json").write_text(
        json.dumps(
            {
                "deck_name": "Plan Override",
                "rules": [],
                "quality": {"blocked_reason": "no_source_backed_mulligan_keeps"},
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "package"

    code = main(
        [
            "build",
            "--deck-name",
            "Plan Override",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--guide-sources-json",
            str(guide_sources),
            "--plan-reports-dir",
            str(plan_reports),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    mulligan = json.loads(
        (out / "CustomConfig" / "plan_override" / "Mulligan.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert mulligan["Mulligan"]["values"] == []
