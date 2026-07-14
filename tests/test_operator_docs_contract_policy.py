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


def test_skill_text_names_source_contract_spine_without_runtime_surface_expansion():
    skill = (ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    reference = (
        ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "guide-research-policy.md"
    ).read_text(encoding="utf-8")
    combined = f"{skill}\n{reference}"

    assert "`claim_kind`" in combined
    assert "source contract matrix" in combined
    assert "surface gate" in combined
    assert "operator_summary.json remains the normal apply authority" in combined
    assert "Warnings are follow-up work, not runtime apply blockers." in combined
    assert "normal HSConfig output must not emit `Presume.json` or `Concede.json`" in combined


def test_operator_docs_keep_one_apply_authority_and_no_second_gate_language():
    operator_readme = (ROOT / "docs/operator/README.md").read_text(encoding="utf-8")
    guide_policy = (ROOT / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    combined = operator_readme + "\n" + guide_policy

    assert "reports/operator_summary.json remains the only normal apply authority" in combined
    assert "source_contract_audit.json is diagnostic" in combined
    assert "`source_advisory_gate` is warning/advisory only" in combined
    assert "Presume.json" in combined
    assert "Concede.json" in combined
    assert "normal-path Presume.json" not in combined
    assert "normal-path Concede.json" not in combined
    assert "normal path Presume.json" not in combined
    assert "normal path Concede.json" not in combined
    assert "block/apply-gate" not in combined


def test_source_contract_spine_reference_is_active_but_not_an_apply_gate():
    text = (ROOT / "docs" / "operator" / "source-contract-spine.md").read_text(
        encoding="utf-8"
    )

    required_claim_kinds = {
        "archetype",
        "mulligan_keep",
        "mulligan_discard",
        "card_role",
        "targeting_rule",
        "combo_sequence",
        "gameplan_posture",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "tech_slot",
        "replacement_option",
        "discover_choice",
        "choose_one_choice",
        "globalvalue_numeric_tuning",
    }

    assert "Diagnostic reference only" in text
    assert "`reports/operator_summary.json` remains the only normal apply authority." in text
    assert "does not create a second apply gate" in text
    assert "Mulligan.json" in text
    assert "GlobalValues.json" in text
    assert "Combo.json" in text
    assert "CARDID.json" in text
    assert "Presume.json" in text
    assert "Concede.json" in text
    for claim_kind in required_claim_kinds:
        assert f"`{claim_kind}`" in text


def test_operator_readme_links_source_contract_spine_without_normal_path_drift():
    text = (ROOT / "docs" / "operator" / "README.md").read_text(encoding="utf-8")
    first_120_lines = "\n".join(text.splitlines()[:120])

    assert "docs/operator/source-contract-spine.md" in text
    assert "hsconfig configure" in first_120_lines
    assert "source-contract-spine" not in first_120_lines
    assert "source-contract-spine -> apply" not in text
