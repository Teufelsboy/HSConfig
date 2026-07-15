from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


FIXTURES = Path(__file__).parent / "fixtures"
SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_source_autopilot_command_writes_inspected_source_artifacts(tmp_path):
    cards_payload = {
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "SW_446", "name": "Voidtouched Attendant", "cost": 1, "count": 2},
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ]
    }
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(json.dumps(cards_payload), encoding="utf-8")
    out = tmp_path / "source"

    status = main(
        [
            "source-autopilot",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--cards-json",
            str(cards_json),
            "--source-search-results-json",
            str(FIXTURES / "source_search_shadowpriest_2026.json"),
            "--out",
            str(out),
            "--json",
        ]
    )

    assert status == 0
    report = json.loads((out / "source_autopilot_report.json").read_text(encoding="utf-8"))
    rows = json.loads((out / "source_evidence_rows.json").read_text(encoding="utf-8"))[
        "evidence_rows"
    ]
    docs = json.loads((out / "source_documents.json").read_text(encoding="utf-8"))

    assert report["strong_candidate"] is True
    assert any(row["claim_kind"] == "hero_power_transform" for row in rows)
    assert docs["source_documents"][0]["claims"]
