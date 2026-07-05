from pathlib import Path

from hsconfig.compile_optional_surfaces import compile_concede, compile_presume
from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_compile_optional_surfaces_return_none_without_policy():
    contract = {"deck_name": "Fixture", "policies": {}}

    assert compile_presume(contract) is None
    assert compile_concede(contract) is None


def test_compile_optional_surfaces_are_runtime_gated_by_default():
    contract = {
        "deck_name": "Fixture Aggro",
        "policies": {
            "presume": [{"rule_id": "presume_1", "value": "assume_secret_pressure"}],
            "concede": [{"rule_id": "concede_1", "value": "concede"}],
        },
    }

    assert compile_presume(contract) is None
    assert compile_concede(contract) is None


def test_compile_optional_surfaces_emit_documented_blocks_when_enabled(tmp_path: Path):
    contract = {
        "deck_name": "Fixture Aggro",
        "policies": {
            "presume": [
                {
                    "rule_id": "presume_1",
                    "condition": "opponent_class == MAGE",
                    "value": "assume_secret_pressure",
                    "source_claim_ids": ["claim_p"],
                }
            ],
            "concede": [
                {
                    "rule_id": "concede_1",
                    "condition": "remaining_health <= 0",
                    "value": "concede",
                    "source_claim_ids": ["claim_c"],
                }
            ],
        },
    }

    presume = compile_presume(contract, enabled=True)
    concede = compile_concede(contract, enabled=True)

    assert presume is not None
    assert concede is not None
    assert presume["PresumeOppInHandCard"]["values"][0]["source_claim_ids"] == ["claim_p"]
    assert concede["ExtraConcdeSettings"]["values"][0]["value"] == "concede"

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "Presume.json", presume)
    write_json(deck_dir / "Concede.json", concede)

    assert validate_config_package(tmp_path)["status"] == "passed"
