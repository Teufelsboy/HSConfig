import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
EXPECTED_DECKS = {
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
}
CORE_FIXTURES = {"BigShaman", "MechPala", "PirateRogue", "ShadowPriest"}
SOURCE_INFORMED_VALID_FIXTURES = EXPECTED_DECKS - CORE_FIXTURES
EXPECTED_DECK_IDENTITIES = {
    "ShadowPriest": {
        "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        "hs_id": "2737726722",
        "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
    },
    "CtAPaladin": {
        "deck_code": "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=",
        "hs_id": "2737744316",
        "hdt_deck_id": "f9b54950-ca24-48cf-805e-bf620eab47a0",
    },
    "PirateRogue": {
        "deck_code": "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==",
        "hs_id": "2740734095",
        "hdt_deck_id": "c1e87d43-5802-460b-b955-31ae458eb41a",
    },
    "BigShaman": {
        "deck_code": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
        "hs_id": "2737735409",
        "hdt_deck_id": "6b26f907-6f1e-44c8-a4e4-d14e9d51f819",
    },
    "Discolock": {
        "deck_code": "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA",
        "hs_id": "2740357533",
        "hdt_deck_id": "55241397-ac74-4d46-a662-089e5858839c",
    },
    "TreantDruid": {
        "deck_code": "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==",
        "hs_id": "2740360895",
        "hdt_deck_id": "a120a28b-1840-4032-a3c9-2da4c51338ed",
    },
    "ImbueMage": {
        "deck_code": "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=",
        "hs_id": "2740361888",
        "hdt_deck_id": "49c05560-8b30-4d06-b3a2-a8b0ff36d005",
    },
    "MechPala": {
        "deck_code": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
        "hs_id": "2740734214",
        "hdt_deck_id": "8f011f55-8ae2-436c-b53a-315f280e8833",
    },
    "Kingslayer": {
        "deck_code": "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=",
        "hs_id": "2740733989",
        "hdt_deck_id": "1292ff02-8ebe-47a5-90b1-9a1899acd6aa",
    },
    "Boarlock": {
        "deck_code": "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA",
        "hs_id": "2740361505",
        "hdt_deck_id": "7727c718-c93c-47ca-a766-5612c3806f0f",
    },
    "PirateDH": {
        "deck_code": "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==",
        "hs_id": "2737737281",
        "hdt_deck_id": "2bc184ed-b59a-4420-900d-b0ed3d153979",
    },
}


def _matrix():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_archetype_fixture_matrix_covers_supplied_decks():
    matrix = _matrix()
    assert matrix["schema_version"] == 1
    decks = {row["deck_name"] for row in matrix["decks"]}
    assert decks == EXPECTED_DECKS


def test_archetype_fixture_matrix_has_actionable_rows():
    for row in _matrix()["decks"]:
        assert row["deck_code"]
        assert row["hs_id"]
        assert row["hdt_deck_id"]
        assert row["archetype_bucket"]
        assert row["primary_mechanics"]
        assert "GlobalValues.json" in row["expected_runtime_surfaces"]
        assert "Mulligan.json" in row["expected_runtime_surfaces"]
        assert "<CARDID>.json" in row["expected_runtime_surfaces"]
        assert row["fixture_stage"] in {
            "core_source_backed_fixture",
            "source_informed_valid_fixture",
            "future_fixture",
        }


def test_archetype_fixture_matrix_uses_supplied_deck_identities():
    for row in _matrix()["decks"]:
        identity = EXPECTED_DECK_IDENTITIES[row["deck_name"]]
        for field in ("deck_code", "hs_id", "hdt_deck_id"):
            assert row[field] == identity[field]
            assert not row[field].startswith("fixture-local")
            assert "fixture-local" not in row[field]


def test_archetype_fixture_matrix_marks_core_wave():
    core = {
        row["deck_name"]
        for row in _matrix()["decks"]
        if row["fixture_stage"] == "core_source_backed_fixture"
    }
    assert core == CORE_FIXTURES


def test_archetype_fixture_matrix_marks_source_informed_valid_wave():
    source_informed = {
        row["deck_name"]
        for row in _matrix()["decks"]
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }
    assert source_informed == SOURCE_INFORMED_VALID_FIXTURES
