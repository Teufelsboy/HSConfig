import json
from pathlib import Path

from hsconfig.cli import main


def test_draft_source_documents_command_writes_documents_and_report(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps({"cards": [{"card_id": "BAR_735", "name": "Darkbishop Benedictus", "count": 1}]}),
        encoding="utf-8",
    )
    evidence_json = tmp_path / "source_evidence.json"
    evidence_json.write_text(
        json.dumps(
            {
                "evidence_rows": [
                    {
                        "source_url": "https://example.invalid/shadow-priest",
                        "source_title": "Shadow Priest Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T12:00:00Z",
                        "claim_kind": "hero_power_transform",
                        "card_mentions": ["Darkbishop Benedictus"],
                        "stance": "enable_transformed_hero_power",
                        "evidence_text_short": "Shadow Priest wants the transformed hero power.",
                        "source_confidence": "high",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "source"

    code = main(
        [
            "draft-source-documents",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "TEST",
            "--cards-json",
            str(cards_json),
            "--source-evidence-json",
            str(evidence_json),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    documents = json.loads((out / "source_documents.json").read_text(encoding="utf-8"))
    report = json.loads((out / "source_document_draft_report.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "OK"
    assert documents["source_documents"][0]["claims"][0]["cards"] == ["BAR_735"]
    assert report["draft_summary"]["resolved_claims"] == 1
    assert report["unresolved_mentions"] == []


def test_draft_source_documents_drops_partial_resolution(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps({"cards": [{"card_id": "BAR_735", "name": "Darkbishop Benedictus", "count": 1}]}),
        encoding="utf-8",
    )
    evidence_json = tmp_path / "source_evidence.json"
    evidence_json.write_text(
        json.dumps(
            {
                "evidence_rows": [
                    {
                        "source_url": "https://example.invalid/shadow-priest",
                        "source_title": "Shadow Priest Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T12:00:00Z",
                        "claim_kind": "card_role",
                        "card_mentions": ["Darkbishop Benedictus", "Missing Card"],
                        "stance": "core_cards",
                        "evidence_text_short": "Two cards are important together.",
                        "source_confidence": "medium",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "source"

    code = main(
        [
            "draft-source-documents",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "TEST",
            "--cards-json",
            str(cards_json),
            "--source-evidence-json",
            str(evidence_json),
            "--out",
            str(out),
            "--json",
        ]
    )

    json.loads(capsys.readouterr().out)
    documents = json.loads((out / "source_documents.json").read_text(encoding="utf-8"))
    report = json.loads((out / "source_document_draft_report.json").read_text(encoding="utf-8"))

    assert code == 0
    assert documents["source_documents"][0]["claims"] == []
    assert report["draft_summary"]["dropped_claims"] == 1
    assert report["unresolved_mentions"][0]["mention"] == "Missing Card"
