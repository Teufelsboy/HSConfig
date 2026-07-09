import json
from pathlib import Path


MATRIX = Path("docs/operator/archetype-fixture-matrix.json")
SUPPLEMENTAL = Path("docs/operator/supplemental-proof-decks.json")


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
