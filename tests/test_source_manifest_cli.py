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
    manifest = json.loads((out / "source_research_manifest.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "OK"
    assert "Mech Paladin" in manifest["search_aliases"]
    assert manifest["mechanic_focus"] == ["mech", "magnetic", "board_scaling"]
    assert payload["written_files"] == [str(out / "source_research_manifest.json")]
