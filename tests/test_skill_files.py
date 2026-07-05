from pathlib import Path


SKILL_ROOT = Path(".agents/skills/hsconfig")


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
    assert "GlobalValues" in text
    assert "no replay analysis" in text.lower()
    assert "validate" in text.lower()
    assert "runtime apply only when the user asks" in text.lower()


def test_skill_scripts_delegate_to_cli():
    for script_name, command in {
        "build_config.py": "build",
        "validate_package.py": "validate",
    }.items():
        text = (SKILL_ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert "from hsconfig.cli import main" in text
        assert command in text
