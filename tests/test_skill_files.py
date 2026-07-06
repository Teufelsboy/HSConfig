from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / "hsconfig"


def test_skill_has_required_files():
    expected = {
        "SKILL.md",
        "references/workflow.md",
        "references/visionai-surfaces.md",
        "references/guide-research-policy.md",
        "references/globalvalues-policy.md",
        "references/card-behavior-policy.md",
        "scripts/build_config.py",
        "scripts/validate_package.py",
    }

    for relative_path in expected:
        assert (SKILL_ROOT / relative_path).exists(), relative_path


def test_skill_content_sets_direct_config_boundary():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

    assert "name: hsconfig" in text
    assert "HearthRanger" in text
    assert "Decode the deck code first" in text
    assert "GlobalValues" in text
    assert "no replay analysis" in text.lower()
    assert "validate" in text.lower()
    assert "runtime apply only when the user asks" in text.lower()
    assert "--allow-placeholder" in text
    assert "hsconfig prepare" in text
    assert "research contract" in text.lower()
    assert "--guide-sources-json" in text


def test_skill_documents_guide_depth_closure_reports():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
    policy = (SKILL_ROOT / "references" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    for text in (skill, workflow, policy):
        assert "per_card_config_readiness_report.json" in text
        assert "guide_source_depth_report.json" in text
    assert "no replay analysis" in skill.lower()
    assert "winrate" in skill.lower()


def test_skill_workflow_documents_deckstring_default_and_runtime_mapping():
    text = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")

    assert "HearthSim deckstring decode" in text
    assert "deckstring_decode_receipt.json" in text
    assert "card_id_map.json" in text
    assert "CustomConfig/deck_config.ini" in text
    assert "--allow-placeholder" in text
    assert "hsconfig prepare" in text
    assert "research-contract" in text
    assert "reports/research" in text
    assert "--guide-sources-json" in text


def test_skill_docs_keep_presume_concede_out_of_normal_path():
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
    surfaces = (SKILL_ROOT / "references" / "visionai-surfaces.md").read_text(encoding="utf-8")

    assert "Presume.json` or `Concede.json`" in text
    assert "normal path" in surfaces
    assert "Presume.json" not in workflow
    assert "Concede.json" not in workflow


def test_guide_research_policy_documents_structured_source_flow():
    skill_policy = (SKILL_ROOT / "references" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    operator_policy = Path("docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    for text in (skill_policy, operator_policy):
        assert "--guide-sources-json" in text
        assert "mulligan_keep" in text
        assert "targeting_rule" in text
        assert "unsupported_claims_report.json" in text
        assert "HSConfig does not" in text or "Do not infer replay performance" in text


def test_globalvalues_policy_mentions_runtime_file_quirks():
    text = (SKILL_ROOT / "references" / "globalvalues-policy.md").read_text(encoding="utf-8")

    assert "UTF-8 BOMs" in text
    assert "trailing commas" in text
    assert "simple numeric expressions" in text


def test_skill_scripts_delegate_to_cli():
    for script_name, command in {
        "build_config.py": "build",
        "validate_package.py": "validate",
    }.items():
        text = (SKILL_ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert "from hsconfig.cli import main" in text
        assert command in text
