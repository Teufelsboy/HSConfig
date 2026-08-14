import hashlib
from pathlib import Path

from hsconfig.io import file_sha256, read_json, slugify_deck_name, write_json
from hsconfig.models import ConfigRow, InputManifest


def test_json_round_trip_and_hash(tmp_path: Path):
    path = tmp_path / "nested" / "data.json"

    write_json(path, {"b": 2, "a": 1})

    assert read_json(path) == {"a": 1, "b": 2}
    assert file_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_read_json_accepts_utf8_bom(tmp_path: Path):
    path = tmp_path / "runtime_globalvalues.json"
    path.write_bytes(b"\xef\xbb\xbf{\"GameCardId\":\"GlobalValues\"}")

    assert read_json(path) == {"GameCardId": "GlobalValues"}


def test_read_json_accepts_visionai_trailing_commas(tmp_path: Path):
    path = tmp_path / "runtime_globalvalues.json"
    path.write_text(
        """
        {
          "GameCardId": "GlobalValues",
          "FirstTurnValueWeight": {
            "values": [
              {
                "condition": "*",
                "value": "0",
              },
            ],
          },
        }
        """,
        encoding="utf-8",
    )

    assert read_json(path) == {
        "GameCardId": "GlobalValues",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
    }


def test_slugify_deck_name_normalizes_names():
    assert slugify_deck_name("Shadow Priest!") == "shadow_priest"
    assert slugify_deck_name("  CtA Paladin  ") == "cta_paladin"
    assert slugify_deck_name("!!!") == "deck"


def test_input_manifest_serializes_to_plain_dict():
    manifest = InputManifest(
        deck_name="ShadowPriest",
        deck_code="AAEBA...",
        runtime_root="C:\\Users\\darbo\\Desktop\\HS",
        target_config_mode="preview",
        format="wild",
    )

    assert manifest.to_dict() == {
        "deck_name": "ShadowPriest",
        "deck_code": "AAEBA...",
        "runtime_root": "C:\\Users\\darbo\\Desktop\\HS",
        "target_config_mode": "preview",
        "format": "wild",
    }


def test_config_row_serializes_defaults():
    row = ConfigRow(
        file_path="CustomConfig/deck/EX1_001.json",
        json_pointer="/InHandBonus/values/0",
        source_rule_id="rule_001",
    )

    assert row.to_dict() == {
        "file_path": "CustomConfig/deck/EX1_001.json",
        "json_pointer": "/InHandBonus/values/0",
        "source_rule_id": "rule_001",
        "source_refs": [],
        "confidence": "source_backed",
    }
