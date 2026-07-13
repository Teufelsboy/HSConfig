from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _compact(text: str) -> str:
    return " ".join(text.lower().split())


def test_guide_research_policy_names_source_truth_boundary():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "Source Truth Is Not Runtime Authority" in text
    assert "`claim_kind` is the runtime-routing authority" in text
    assert "`operator_summary.json` remains the only normal apply authority" in text
    assert "Darkbishop Benedictus" in text
    assert "does not become a mulligan keep" in text
    assert "`globalvalue_numeric_tuning`" in text
    assert "requires runtime evidence" in text


def test_guide_research_policy_keeps_no_block_language():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "Warnings are follow-up work, not a runtime apply blocker." in text
    assert "Do not use `source_contract_audit.json` as an apply gate." in text


def test_operator_docs_name_canonical_lifecycle_without_second_gate():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    normalized = _compact(text)

    assert "canonical claim lifecycle" in normalized
    assert "conflict quarantine" in normalized
    assert "quarantined claims suppress unsafe runtime rows" in normalized
    assert "do not block load-safe valid packages" in normalized
    assert "operator_summary.json remains the only normal apply authority" in text
    assert "source_contract_audit.json is diagnostic" in text


def test_skill_mentions_claim_lifecycle_and_no_block_contract():
    text = (ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "canonical claim lifecycle" in text.lower()
    assert "quarantined claims suppress unsafe runtime rows" in text
    assert "do not block load-safe valid packages" in text


def test_skill_reference_mentions_claim_lifecycle_and_no_block_contract():
    text = (
        ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "guide-research-policy.md"
    ).read_text(encoding="utf-8")
    normalized = _compact(text)

    assert "canonical claim lifecycle" in normalized
    assert "conflict quarantine" in normalized
    assert "quarantined claims suppress unsafe runtime rows" in normalized
    assert "do not block load-safe valid packages" in normalized
    assert "operator_summary.json remains the only normal apply authority" in text
    assert "source_contract_audit.json" in text
