from pathlib import Path


def test_research_docs_are_marked_as_evidence_not_operator_path():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in text
    assert "Normal operator path starts at `docs/operator/README.md`." in text


def test_root_readme_points_to_operator_path_not_research_history():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "docs/operator/README.md" in text
    assert "docs/research/" not in text


def test_operator_docs_mark_research_artifacts_as_evidence():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in text


def test_operator_docs_explain_runtime_apply_mode_is_descriptive():
    operator_docs = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "runtime_load_safe" in operator_docs
    assert "runtime_apply_mode" in operator_docs
    assert "runtime_apply_allowed" in operator_docs
    assert "ALLOWED_WITH_WARNINGS` is runtime write permission when `technical_status=VALID_PACKAGE`" in operator_docs
