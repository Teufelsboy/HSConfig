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
    assert "runtime apply is allowed after validation" in text.lower()
    assert "--allow-placeholder" in text
    assert "hsconfig prepare" in text
    assert "hsconfig research-deck" in text
    assert "operator_summary.json" in text
    assert "research contract" in text.lower()
    assert "--guide-sources-json" in text


def test_skill_docs_preserve_hsconfig_boundaries_without_verbatim_duplication():
    docs = [
        Path("README.md").read_text(encoding="utf-8"),
        Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
        Path(".agents/skills/hsconfig/references/workflow.md").read_text(
            encoding="utf-8"
        ),
    ]
    joined = "\n".join(docs)
    required_terms = {
        "research-deck",
        "prepare",
        "operator_summary.json",
        "VALID_PACKAGE",
        "SOURCE_BACKED_STRONG",
        "STATIC_SEMANTICS_USABLE",
        "VALID_BUT_NOT_GUIDE_STRONG",
        "HSTuner",
        "Presume.json",
        "Concede.json",
    }

    for term in required_terms:
        assert term in joined


def test_skill_docs_do_not_call_static_semantics_optimized():
    active_files = [
        REPO_ROOT / "README.md",
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "references" / "workflow.md",
    ]
    forbidden = [
        "static semantics are optimized",
        "valid package means optimized",
        "no guide research needed",
    ]

    for path in active_files:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden:
            assert phrase not in text


def test_active_docs_show_normal_source_document_operator_path():
    active_files = [
        REPO_ROOT / "README.md",
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "references" / "workflow.md",
    ]
    required_terms = {
        "source_documents.json",
        "hsconfig research-deck --source-documents-json",
        "hsconfig prepare --guide-sources-json",
        "operator_summary.json",
        "hsconfig apply",
        "only when requested",
    }

    for path in active_files:
        text = path.read_text(encoding="utf-8")
        for term in required_terms:
            assert term in text


def test_guide_policy_documents_source_depth_contract():
    skill_policy = (SKILL_ROOT / "references" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    operator_policy = Path("docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    required_terms = {
        "source_url",
        "source_title",
        "source_family",
        "retrieved_at",
        "deck_name",
        "archetype",
        "claim_kind",
        "evidence_text_short",
        "source_confidence",
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
        "claim freshness",
        "claim_conflict_report.json",
        "every-card coverage",
        "DROPn",
        "plus-combo",
        "wildcard",
        "explicit discard",
        "runtime_block",
        "BeforePlayCardBonus",
        "OnDiscoverCardBonus",
        "timing_kind",
        "global_values_key_profile_report.json",
        "authority_category",
    }

    for text in (skill_policy, operator_policy):
        for term in required_terms:
            assert term in text


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
    assert "research-deck" in text
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


def test_skill_docs_describe_cardid_runtime_block_lowering():
    root = Path(".agents/skills/hsconfig")
    card_policy = (root / "references" / "card-behavior-policy.md").read_text(
        encoding="utf-8"
    )
    guide_policy = (root / "references" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "runtime_block" in guide_policy
    assert "BeforeOverkilledBonus" in card_policy
    assert "meaningful_runtime_surface" in card_policy
    assert "Presume.json" in card_policy
    assert "Concede.json" in card_policy


def test_guide_research_policy_documents_structured_source_flow():
    skill_policy = (SKILL_ROOT / "references" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    operator_policy = Path("docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    for text in (skill_policy, operator_policy):
        assert "--source-documents-json" in text
        assert "--guide-sources-json" in text
        assert "research-deck" in text
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


def test_skill_docs_explain_valid_package_vs_source_backed_strong():
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "VALID_PACKAGE" in docs
    assert "SOURCE_BACKED_STRONG" in docs
    assert "guide_strength_summary" in docs
    assert "semantic_blockers" in docs
    assert "HSConfig does not parse replays" in docs
    assert "Presume.json" in docs
    assert "Concede.json" in docs


def test_readme_documents_installed_skill_sync():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "scripts/sync_installed_skill.py --check" in text
    assert "scripts/sync_installed_skill.py" in text
