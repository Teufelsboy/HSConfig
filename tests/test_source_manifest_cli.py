import json
from pathlib import Path

from hsconfig.cli import main


def test_source_manifest_command_writes_research_manifest(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps({"cards": [{"card_id": "BOT_001", "name": "Mech Example", "count": 2}]}),
        encoding="utf-8",
    )
    out = tmp_path / "manifest"

    code = main(
        [
            "source-manifest",
            "--deck-name",
            "MechPala",
            "--deck-code",
            "TEST",
            "--cards-json",
            str(cards_json),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    manifest_path = out / "source_research_manifest.json"
    candidate_plan_path = out / "source_candidate_plan.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_plan = json.loads(candidate_plan_path.read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "OK"
    assert "Mech Paladin" in manifest["search_aliases"]
    assert manifest["mechanic_focus"] == ["mech", "magnetic", "board_scaling"]
    assert candidate_plan["authority"] == "diagnostic_source_candidate_plan"
    assert candidate_plan["apply_blocking"] is False
    assert candidate_plan["source_status_apply_blocking"] is False
    assert candidate_plan["candidate_registry_url_count"] >= 1
    assert candidate_plan["queries"]
    assert payload["written_files"] == [str(manifest_path), str(candidate_plan_path)]
