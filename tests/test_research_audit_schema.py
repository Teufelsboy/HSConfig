import json
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


def _assert_results_cover_required_fields(fields: Path, result_files: list[Path]) -> None:
    payload = yaml.safe_load(fields.read_text(encoding="utf-8"))
    required_fields = {
        field["name"]
        for category in payload["field_categories"]
        for field in category["fields"]
        if field.get("required") is True
    }
    for path in result_files:
        result = json.loads(path.read_text(encoding="utf-8"))
        assert required_fields <= set(result), path


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
    result_files = sorted(RESULTS.glob("*.json"))

    assert len(result_files) == 5
    _assert_results_cover_required_fields(FIELDS, result_files)


def test_research_index_marks_research_as_evidence_not_operator_guidance():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in text
    assert "2026-07-08-hsconfig-final-skill-audit" in text
    assert "docs/operator/README.md remains the normal operator entrypoint." in text


def test_current_skill_lean_audit_package_is_indexed_as_evidence():
    readme = Path("docs/research/README.md").read_text(encoding="utf-8")
    audit_root = Path("docs/research/2026-07-08-hsconfig-current-skill-lean-audit")

    assert "2026-07-08-hsconfig-current-skill-lean-audit" in readme
    assert "current skill lean audit" in readme.lower()
    assert "evidence, not operator instructions" in readme.lower()
    assert (audit_root / "fields.yaml").exists()
    assert (audit_root / "outline.yaml").exists()
    assert len(list((audit_root / "results").glob("*.json"))) == 5


def test_source_builder_lite_research_results_validate():
    audit_dir = Path("docs/research/2026-07-07-hsconfig-source-builder-lite")
    fields = audit_dir / "fields.yaml"
    results = audit_dir / "results"
    result_files = sorted(results.glob("*.json"))
    assert len(result_files) == 5

    _assert_results_cover_required_fields(fields, result_files)


def test_latest_guarded_apply_matrix_audit_is_curated_markdown():
    path = Path("docs/research/2026-07-08-hsconfig-guarded-apply-matrix-audit.md")
    text = path.read_text(encoding="utf-8")

    assert "Guarded Apply" in text
    assert "Matrix Governance" in text
    assert "VisionAI Registry Micro-Wave" in text
    assert "Research artifacts are evidence, not operator instructions." in text


def test_new_research_fields_are_not_empty_contracts():
    research_dirs = [
        path
        for path in Path("docs/research").iterdir()
        if path.is_dir() and path.name >= "2026-07-08-hsconfig-guarded"
    ]
    for folder in research_dirs:
        fields = folder / "fields.yaml"
        if not fields.exists():
            continue
        payload = yaml.safe_load(fields.read_text(encoding="utf-8"))
        categories = payload.get("field_categories", [])
        names = [
            field["name"]
            for category in categories
            for field in category.get("fields", [])
        ]
        if not names:
            names = list(payload.get("fields", {}))
        assert names, f"{fields} must define required research fields"


def test_post_hardening_skill_audit_is_indexed_as_evidence_only():
    root = Path("docs/research/2026-07-11-hsconfig-post-hardening-skill-audit")
    readme = (root / "README.md").read_text(encoding="utf-8")
    current_truth = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in readme
    assert "Normal operation starts at `README.md` and `docs/operator/README.md`." in readme
    assert "post-hardening skill audit evidence" in current_truth.lower()
    assert "2026-07-11-hsconfig-post-hardening-skill-audit" in current_truth


def test_source_contract_logic_audit_validates_and_is_indexed_as_evidence():
    root = Path("docs/research/2026-07-11-hsconfig-source-contract-logic-audit")
    fields = root / "fields.yaml"
    results = root / "results"
    result_files = sorted(results.glob("*.json"))
    assert len(result_files) == 3

    assert len(
        {
            field["name"]
            for category in yaml.safe_load(fields.read_text(encoding="utf-8"))["field_categories"]
            for field in category["fields"]
            if field.get("required") is True
        }
    ) == 8
    _assert_results_cover_required_fields(fields, result_files)

    readme = (root / "README.md").read_text(encoding="utf-8")
    current_truth = Path("docs/research/current-truth.md").read_text(encoding="utf-8")
    assert "Research artifacts are evidence, not operator instructions." in readme
    assert "claim-kind runtime contract closure" in readme
    assert "2026-07-11-hsconfig-source-contract-logic-audit" in current_truth
