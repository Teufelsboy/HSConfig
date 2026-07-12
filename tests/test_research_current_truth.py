from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_current_truth_links_source_contract_brainstorm_package():
    text = (ROOT / "docs" / "research" / "current-truth.md").read_text(
        encoding="utf-8"
    )

    assert "2026-07-12-hsconfig-source-contract-slim-autonomy-brainstorm" in text
    assert "source-contract spine" in text.lower()
    assert "operator_summary.json remains the only normal apply authority" in text


def test_current_truth_does_not_turn_research_into_apply_authority():
    text = (ROOT / "docs" / "research" / "current-truth.md").read_text(
        encoding="utf-8"
    )

    forbidden = [
        "source_contract_audit.json authorizes apply",
        "contract_doctor authorizes apply",
        "research authorizes runtime writes",
    ]
    for phrase in forbidden:
        assert phrase not in text.lower()
