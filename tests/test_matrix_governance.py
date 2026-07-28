import json
from pathlib import Path

from hsconfig.input_loading import fixture_row_for


MATRIX = Path("docs/operator/archetype-fixture-matrix.json")
SUPPLEMENTAL = Path("docs/operator/supplemental-proof-decks.json")
SOURCE_CANDIDATES = Path("docs/operator/source-candidate-proof-decks.json")
CATALOG = Path("docs/operator/audited-deck-catalog.json")
IDENTITY_FIELDS = {"deck_code", "hs_id", "hdt_deck_id", "matrix_role"}


def test_role_manifests_reference_catalog_without_duplicating_identity():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    supplemental = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    candidates = json.loads(SOURCE_CANDIDATES.read_text(encoding="utf-8"))
    catalog_names = {row["deck_name"] for row in catalog["decks"]}
    representative_names = {
        row["deck_name"]
        for row in catalog["decks"]
        if row["matrix_role"] == "representative"
    }

    for manifest in (matrix, supplemental, candidates):
        assert manifest["identity_catalog"] == "audited-deck-catalog.json"

    assert {row["deck_name"] for row in matrix["decks"]} == representative_names
    assert all(IDENTITY_FIELDS.isdisjoint(row) for row in matrix["decks"])

    audited_supplemental = [
        row for row in supplemental["decks"] if row["deck_name"] in catalog_names
    ]
    visibility_only = [
        row for row in supplemental["decks"] if row["deck_name"] not in catalog_names
    ]
    assert [row["deck_name"] for row in audited_supplemental] == ["CuteWarrior"]
    assert all(IDENTITY_FIELDS.isdisjoint(row) for row in audited_supplemental)
    assert {row["deck_name"] for row in visibility_only} == {
        "SecretMage",
        "HighlanderPriest",
    }
    assert all(row["deck_code"] for row in visibility_only)

    assert {row["deck_name"] for row in candidates["decks"]} == catalog_names
    assert all(IDENTITY_FIELDS.isdisjoint(row) for row in candidates["decks"])


def test_fixture_role_loader_resolves_identity_from_catalog():
    shadowpriest = fixture_row_for("ShadowPriest")

    assert shadowpriest is not None
    assert shadowpriest["deck_code"].startswith("AAEBAa0G")
    assert shadowpriest["hs_id"] == "2737726722"
    assert shadowpriest["hdt_deck_id"] == ("c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602")
    assert shadowpriest["matrix_role"] == "representative"
    assert shadowpriest["archetype_bucket"] == ("aggro_burn_hero_power_transform")


def test_representative_matrix_stays_eleven_rows_until_explicitly_widened():
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    names = [row["deck_name"] for row in matrix["decks"]]

    assert len(names) == 11
    assert "CuteWarrior" not in names
    assert {"Kingslayer", "Boarlock"} <= set(names)


def test_supplemental_proof_decks_are_not_representative_matrix_rows():
    supplemental = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    rows = supplemental["decks"]

    assert rows
    cute = next(row for row in rows if row["deck_name"] == "CuteWarrior")
    assert cute["proof_role"] == "supplemental_load_safe_prepare_proof"
    assert (
        cute["matrix_policy"]
        == "not_representative_until_future_matrix_review_proves_missing_family"
    )
    assert cute["operator_action"] == "keep_supplemental"
