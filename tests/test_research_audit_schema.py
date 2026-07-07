import json
import subprocess
import sys
from pathlib import Path

import yaml


AUDIT_DIR = Path("docs/research/2026-07-07-hsconfig-skill-audit")
FIELDS = AUDIT_DIR / "fields.yaml"
RESULTS = AUDIT_DIR / "results"
EXPECTED_FIELDS = {
    "source_summary",
    "current_truth",
    "repo_alignment",
    "gaps_or_risks",
    "recommended_action",
    "confidence",
    "citations",
    "uncertain",
}


def test_skill_audit_fields_yaml_uses_research_validator_shape():
    payload = yaml.safe_load(FIELDS.read_text(encoding="utf-8"))
    categories = payload["field_categories"]
    names = {
        field["name"]
        for category in categories
        for field in category["fields"]
    }
    required = {
        field["name"]
        for category in categories
        for field in category["fields"]
        if field.get("required") is True
    }

    assert names == EXPECTED_FIELDS
    assert required == EXPECTED_FIELDS


def test_skill_audit_research_results_cover_all_required_fields():
    result_files = sorted(RESULTS.glob("*.json"))
    assert len(result_files) == 5
    for path in result_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert EXPECTED_FIELDS <= set(data)
        assert isinstance(data["gaps_or_risks"], list)
        assert isinstance(data["citations"], list)
        assert isinstance(data["uncertain"], list)


def test_skill_audit_results_pass_existing_research_validator():
    command = [
        sys.executable,
        str(Path.home() / ".codex/skills/research/validate_json.py"),
        "-f",
        str(FIELDS),
        "-j",
        *[str(path) for path in sorted(RESULTS.glob("*.json"))],
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Total fields: 8" in completed.stdout
    assert "Validation passed: 5/5" in completed.stdout


def test_source_builder_lite_research_results_validate():
    audit_dir = Path("docs/research/2026-07-07-hsconfig-source-builder-lite")
    fields = audit_dir / "fields.yaml"
    results = audit_dir / "results"
    result_files = sorted(results.glob("*.json"))
    assert len(result_files) == 5

    command = [
        sys.executable,
        str(Path.home() / ".codex/skills/research/validate_json.py"),
        "-f",
        str(fields),
        "-j",
        *[str(path) for path in result_files],
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Validation passed: 5/5" in completed.stdout
