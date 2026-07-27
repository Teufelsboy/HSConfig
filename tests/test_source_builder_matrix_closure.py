from pathlib import Path

from hsconfig.matrix_closure import build_matrix_closure_summary
from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


ROOT = Path(__file__).resolve().parents[1]


def test_all_matrix_rows_have_source_fixture_files():
    missing = []
    for row in load_archetype_matrix():
        fixture_name = f"source_documents_{row['deck_name'].lower()}_strong.json"
        if not (ROOT / "tests" / "fixtures" / fixture_name).exists():
            missing.append(fixture_name)
    assert missing == []


def test_matrix_closure_summary_is_machine_readable(tmp_path: Path):
    rows = load_archetype_matrix()
    results = {}
    for row in rows:
        prepared = prepare_fixture_deck(tmp_path, row)
        results[row["deck_name"]] = {
            "operator": prepared["operator"],
            "source_gap": prepared["source_gap"],
        }

    summary = build_matrix_closure_summary(matrix_rows=rows, results=results)

    assert summary["summary"]["deck_count"] == 11
    assert summary["summary"]["valid_package_count"] == 11
    assert summary["summary"]["source_backed_strong_count"] == 0
    assert set(summary["decks"]) == {row["deck_name"] for row in rows}
