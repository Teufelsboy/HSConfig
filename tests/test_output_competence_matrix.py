import json
from pathlib import Path

import pytest

from hsconfig.cli import main


SOURCE_DOCS = {
    "ShadowPriest": "tests/fixtures/source_documents_shadowpriest_strong.json",
    "CtAPaladin": "tests/fixtures/source_documents_ctapaladin_strong.json",
    "PirateRogue": "tests/fixtures/source_documents_piraterogue_strong.json",
    "BigShaman": "tests/fixtures/source_documents_bigshaman_strong.json",
    "Discolock": "tests/fixtures/source_documents_discolock_strong.json",
    "TreantDruid": "tests/fixtures/source_documents_treantdruid_strong.json",
    "Kingslayer": "tests/fixtures/source_documents_kingslayer_strong.json",
    "ImbueMage": "tests/fixtures/source_documents_imbuemage_strong.json",
    "MechPala": "tests/fixtures/source_documents_mechpala_strong.json",
    "Boarlock": "tests/fixtures/source_documents_boarlock_strong.json",
    "PirateDH": "tests/fixtures/source_documents_piratedh_strong.json",
}

EXPECTED_REPRESENTATIVE_DECK_NAMES = {
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "Kingslayer",
    "ImbueMage",
    "MechPala",
    "Boarlock",
    "PirateDH",
}


def _representative_decks() -> list[dict]:
    matrix = json.loads(
        Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8")
    )
    return [
        row
        for row in matrix["decks"]
        if row["fixture_stage"] in {"core_source_backed_fixture", "source_informed_valid_fixture"}
    ]


def test_representative_deck_set_is_exact():
    representative_decks = _representative_decks()

    assert set(SOURCE_DOCS) == EXPECTED_REPRESENTATIVE_DECK_NAMES
    assert len(representative_decks) == 11
    assert {row["deck_name"] for row in representative_decks} == EXPECTED_REPRESENTATIVE_DECK_NAMES


@pytest.mark.parametrize("deck", _representative_decks(), ids=lambda row: row["deck_name"])
def test_representative_decks_expose_output_competence_summary(
    tmp_path: Path,
    capsys,
    monkeypatch,
    deck: dict,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / deck["deck_name"]
    args = [
        "prepare",
        "--deck-name",
        deck["deck_name"],
        "--deck-code",
        deck["deck_code"],
        "--runtime-root",
        str(tmp_path / "runtime"),
        "--out",
        str(out),
        "--source-documents-json",
        SOURCE_DOCS[deck["deck_name"]],
        "--json",
    ]

    code = main(args)
    capsys.readouterr()
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    usefulness = operator["config_usefulness"]

    assert code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_allowed"] is True
    assert usefulness["runtime_permission_impact"] == "none"
    assert usefulness["status"] in {
        "guide_aligned",
        "usable_with_targeted_gaps",
        "load_safe_but_thin",
    }
    assert usefulness["surfaces"]["mulligan"]["status"] in {"rich", "thin", "report_only"}
    assert "changed_key_count" in usefulness["surfaces"]["globalvalues"]
    assert "meaningful_cardid_row_count" in usefulness["surfaces"]["cardid_behavior"]
    assert "combo_row_count" in usefulness["surfaces"]["combo"]

    if "Combo.json" in deck["expected_runtime_surfaces"]:
        assert usefulness["surfaces"]["combo"]["combo_expected"] is True


def test_cute_warrior_remains_supplemental_load_safe_only():
    supplemental = json.loads(
        Path("docs/operator/supplemental-proof-decks.json").read_text(encoding="utf-8")
    )
    cute = next(row for row in supplemental["decks"] if row["deck_name"] == "CuteWarrior")

    assert cute["proof_scope"] == "supplemental_load_safe_only"
    assert cute["representative_output_competence"] is False
