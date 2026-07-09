from pathlib import Path


def test_research_docs_are_marked_as_evidence_not_operator_path():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in text
    assert "Normal operator path starts at `docs/operator/README.md`." in text
    assert "docs/research/current-truth.md" in text
    assert "Use it as the only place that names the active evidence packages" in text
    assert "Active Research Packages" not in text
    assert "Historical evidence examples" in text
    assert "2026-07-09-hsconfig-universal-wild-skill-audit" not in text


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
    assert "load_safe_apply" in operator_docs
    assert (
        "ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE"
        in operator_docs
    )
    assert "ALLOWED_WITH_WARNINGS is not runtime write permission" not in operator_docs


def test_operator_docs_describe_no_block_static_semantics():
    operator_docs = Path("docs/operator/README.md").read_text(encoding="utf-8")
    skill_text = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")

    for text in (operator_docs, skill_text):
        assert "semantic_enrichment_report.json" in text
        assert "warning-only mechanics do not block load-safe apply" in text
    assert "GlobalValues" in skill_text
    assert "Mulligan" in skill_text


def test_research_current_truth_index_exists_and_keeps_operator_boundary():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "HSConfig Current Truth Index" in text
    assert "Research artifacts are evidence, not operator instructions." in text
    assert "Normal operator path starts at `docs/operator/README.md`." in text
    assert "2026-07-09-hsconfig-next-recommendation-mechanic-polish" in text
    assert "Visibility-only Mechanic Polish" in text


def test_research_readme_points_to_current_truth_index():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "docs/research/current-truth.md" in text
    assert "Current truth index" in text
    assert ("current truth file" in text) or (
        "only place that names the active evidence packages" in text
    )
