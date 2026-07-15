import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.io import read_json, write_json
from tests.helpers.fixture_prepare import (
    load_archetype_matrix,
    prepare_fixture_deck,
    read_json as read_fixture_json,
)


DECKS = {
    "ShadowPriest": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    "MechPala": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
    "BigShaman": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
}

EXPECTED_EVIDENCE_STATUS = {
    "ShadowPriest": "SOURCE_BACKED_STRONG",
    "MechPala": "SOURCE_BACKED_STRONG",
    "PirateRogue": "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
    "BigShaman": "SOURCE_BACKED_STRONG",
    "Boarlock": "SOURCE_BACKED_PARTIAL",
    "ImbueMage": "SOURCE_BACKED_STRONG",
    "TreantDruid": "SOURCE_BACKED_PARTIAL",
    "Discolock": "SOURCE_BACKED_PARTIAL",
    "PirateDH": "SOURCE_BACKED_PARTIAL",
    "CtAPaladin": "SOURCE_BACKED_PARTIAL_UNLESS_EXACT_GUIDE_MATCHED",
    "Kingslayer": "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH",
}


@pytest.mark.parametrize("deck_name,deck_code", DECKS.items())
def test_multideck_source_backed_prepare(tmp_path: Path, deck_name: str, deck_code: str):
    fixture = json.loads(
        Path("tests/fixtures/source_documents_multiarchetype.json").read_text(
            encoding="utf-8"
        )
    )
    source_path = tmp_path / f"{deck_name}_sources.json"
    write_json(source_path, fixture[deck_name])
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
            "--source-documents-json",
            str(source_path),
            "--json",
        ]
    )

    assert code == 0
    summary = read_json(out / "reports" / "operator_summary.json")
    assert summary["technical_status"] == "VALID_PACKAGE"
    if deck_name == "ShadowPriest":
        assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
        assert summary["guide_strength_summary"]["cards_needing_runtime_surface"] == 0
        assert summary["semantic_blockers"] == []
    else:
        assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
        assert summary["guide_strength_summary"]["cards_needing_runtime_surface"] > 0
        assert summary["semantic_blockers"]


def prepare_representative_source_matrix(tmp_path: Path) -> list[dict]:
    results = []
    for deck in load_archetype_matrix():
        prepared = prepare_fixture_deck(tmp_path, deck)
        operator = prepared["operator"]
        fixture = read_fixture_json(
            Path(f"tests/fixtures/source_documents_{deck['deck_name'].lower()}_strong.json")
        )
        documents = fixture["source_documents"] if isinstance(fixture, dict) else fixture
        deck_match_scopes = {
            str(row.get("deck_match_scope"))
            for document in documents
            for row in [document, *document.get("claims", [])]
            if row.get("deck_match_scope")
        }
        results.append(
            {
                "deck_name": deck["deck_name"],
                "technical_status": operator["technical_status"],
                "runtime_apply_allowed": operator["runtime_apply_allowed"],
                "semantic_status": operator["semantic_status"],
                "deck_match_scopes": deck_match_scopes,
                "out": prepared["out"],
            }
        )
    return results


def test_representative_decks_do_not_fake_source_backed_strong(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    results = prepare_representative_source_matrix(tmp_path)

    assert {row["deck_name"] for row in results} == set(EXPECTED_EVIDENCE_STATUS)
    for row in results:
        expected = EXPECTED_EVIDENCE_STATUS[row["deck_name"]]
        if expected == "SOURCE_BACKED_STRONG":
            assert row["semantic_status"] == "SOURCE_BACKED_STRONG", row
        elif expected == "SOURCE_BACKED_PARTIAL":
            assert row["technical_status"] == "VALID_PACKAGE", row
            assert row["runtime_apply_allowed"] is True, row
            assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
        elif expected == "SOURCE_BACKED_STRONG_OR_PARTIAL_BY_LIST_MATCH":
            assert row["technical_status"] == "VALID_PACKAGE", row
            assert row["runtime_apply_allowed"] is True, row
            assert row["semantic_status"] in {
                "SOURCE_BACKED_STRONG",
                "VALID_BUT_NOT_GUIDE_STRONG",
                "STATIC_SEMANTICS_USABLE",
            }, row
            if "archetype_matched_not_exact_list" in row["deck_match_scopes"]:
                assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
        elif expected == "SOURCE_BACKED_PARTIAL_UNLESS_EXACT_GUIDE_MATCHED":
            assert row["technical_status"] == "VALID_PACKAGE", row
            assert row["runtime_apply_allowed"] is True, row
            if "deck_or_archetype_matched" not in row["deck_match_scopes"]:
                assert row["semantic_status"] != "SOURCE_BACKED_STRONG", row
        else:
            raise AssertionError(f"unhandled expected evidence status: {expected}")
