import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_research_deck_writes_static_fallback_artifacts(tmp_path: Path, capsys):
    out = tmp_path / "research"

    code = main(
        [
            "research-deck",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    receipt = json.loads((out / "guide_builder_receipt.json").read_text(encoding="utf-8"))
    identity = json.loads((out / "identity_graph_report.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "OK"
    assert payload["source_depth_status"] == "static_semantics_only"
    assert receipt["static_card_semantics_used"] is True
    assert identity["hearthstonejson_receipt"]["status"] == "skipped"
    assert (out / "deck_fingerprint.json").exists()
    assert (out / "candidate_archetypes.json").exists()
    assert (out / "guide_sources.json").exists()
    assert (out / "identity_graph_report.json").exists()
    assert not (out / "CustomConfig").exists()


def test_research_deck_accepts_source_documents_json(tmp_path: Path, capsys):
    source_documents = tmp_path / "source_documents.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_id": "shadow-guide",
                        "source_url": "https://example.invalid/shadow-priest",
                        "source_title": "Shadow Priest Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-06T00:00:00Z",
                        "deck_name": "ShadowPriest",
                        "archetype": "aggro_burn",
                        "claims": [
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": ["SW_448"],
                                "condition": {"coin": True},
                                "reason": "Keep Darkbishop Benedictus.",
                            },
                            {
                                "claim_kind": "gameplan_posture",
                                "scope": "deck",
                                "stance": "aggro_burn",
                                "reason": "Push damage.",
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "research"

    code = main(
        [
            "research-deck",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    guide_sources = json.loads((out / "guide_sources.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["source_depth_status"] == "source_backed"
    assert guide_sources["sources"][0]["claims"][0]["claim_id"].startswith("claim_")
    assert len(guide_sources["sources"][0]["claims"]) == 2


def test_research_deck_rejects_malformed_source_documents_json(tmp_path: Path, capsys):
    bad_source_documents = tmp_path / "source_documents.json"
    bad_source_documents.write_text('{"source_documents": "bad"}', encoding="utf-8")

    code = main(
        [
            "research-deck",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(tmp_path / "research"),
            "--source-documents-json",
            str(bad_source_documents),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "failed"
    assert "--source-documents-json" in payload["errors"][0]
