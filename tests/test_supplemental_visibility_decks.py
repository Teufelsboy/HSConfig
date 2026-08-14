import json
from pathlib import Path

import pytest

from hsconfig.cli import main


SUPPLEMENTAL_PATH = Path("docs/operator/supplemental-proof-decks.json")


VISIBILITY_DECKS = {
    "SecretMage": {
        "deck_code": "AAEBAf0EAA/3Dde2Auu6Aoe9Ar6kA/SrA5HhA+efBMagBKPkBP7sBLztBP+SBduhBejoBQAA",
        "expected_mechanics": {"secret", "secret_timing"},
    },
    "HighlanderPriest": {
        "deck_code": "AAEBAa0GHvcTg7sCtbsC1cECkNMC/KMDlc0D184D+OMDn+sDrfcDvp8EhKMEi6ME5bAEx7IEmtQEhoMF4qQF/cQF5uQF44AG7YAGhY4Gw5wGxpwGzZ4G0Z4G054GvqIGAAABA9fOA/3EBfnbBP3EBcChBv3EBQAA",
        "expected_mechanics": {"highlander", "location", "silence", "destroy"},
    },
}


def _supplemental_decks() -> dict[str, dict]:
    payload = json.loads(SUPPLEMENTAL_PATH.read_text(encoding="utf-8"))
    return {row["deck_name"]: row for row in payload["decks"]}


def test_supplemental_visibility_decks_are_not_representative_rows():
    rows = _supplemental_decks()

    for deck_name, expected in VISIBILITY_DECKS.items():
        row = rows[deck_name]
        assert row["proof_scope"] == "supplemental_visibility_only"
        assert row["representative_output_competence"] is False
        assert row["matrix_policy"] == "not_representative_visibility_only"
        assert set(row["primary_mechanics"]) >= expected["expected_mechanics"]
        assert row["deck_code"] == expected["deck_code"]
        assert row["operator_action"] == "keep_supplemental_visibility"


@pytest.mark.parametrize("deck_name", sorted(VISIBILITY_DECKS))
def test_supplemental_visibility_deck_prepare_is_load_safe(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck_name: str,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    deck_code = VISIBILITY_DECKS[deck_name]["deck_code"]
    out = tmp_path / deck_name

    code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    deck_dirs = [path for path in (out / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["mechanic_visibility_summary"]["non_blocking"] is True
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
