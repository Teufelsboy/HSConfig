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
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    operator_path_files = [
        REPO_ROOT / "docs" / "operator" / "README.md",
        SKILL_ROOT / "SKILL.md",
        SKILL_ROOT / "references" / "workflow.md",
    ]
    required_terms = {
        "source_documents.json",
        "hsconfig research-deck --source-documents-json",
        "hsconfig prepare --guide-sources-json",
        "operator_summary.json",
        "hsconfig apply",
    }

    assert "docs/operator/README.md" in root_readme
    assert "hsconfig source-manifest" in root_readme
    assert "only when requested" in root_readme

    for path in operator_path_files:
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
    assert (
        "HSConfig is pre-run only. It does not parse replays, inspect winrate, "
        "analyze runtime logs, promote candidates, or tune after games."
    ) in docs
    assert "Presume.json" in docs
    assert "Concede.json" in docs


def test_readme_documents_installed_skill_sync():
    text = Path("README.md").read_text(encoding="utf-8")
    normalized = text.replace("\\", "/")

    assert "scripts/sync_installed_skill.py --check" in normalized
    assert "scripts/sync_installed_skill.py" in normalized


def test_docs_make_operator_summary_the_single_normal_gate():
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert docs.count("operator_summary.json") >= 3
    assert "single operator gate" in docs.lower()
    assert "replay" in docs.lower()
    assert "does not parse replays" in docs


def test_docs_do_not_advertise_presume_concede_as_normal_outputs():
    active_docs = [
        Path("README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    forbidden = [
        "emit Presume.json",
        "emit Concede.json",
        "normal output includes Presume",
        "normal output includes Concede",
    ]
    for path in active_docs:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text


def test_skill_docs_explain_strong_fixture_truth_contract():
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "SOURCE_BACKED_STRONG" in docs
    assert "operator_summary.json" in docs
    assert "single operator gate" in docs.lower()
    assert "core_source_backed_fixture" in docs
    assert "source_informed_valid_fixture" in docs
    assert "Presume.json" in docs
    assert "Concede.json" in docs
    assert "not emit" in docs.lower() or "not part of the normal path" in docs.lower()


def test_skill_documents_source_builder_lite_workflow():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
    operator = (REPO_ROOT / "docs" / "operator" / "source-builder-workflow.md").read_text(
        encoding="utf-8"
    )

    combined = "\n".join([skill, workflow, operator])
    assert "source-manifest" in combined
    assert "draft-source-documents" in combined
    assert "source_documents.json" in combined
    assert "operator_summary.json" in combined
    assert "Presume.json" not in operator
    assert "Concede.json" not in operator


def test_current_skill_audit_is_marked_as_research_evidence():
    root = Path("docs/research/2026-07-07-hsconfig-current-skill-audit")
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "research evidence" in readme
    assert "not operator guidance" in readme
    assert "not runtime input" in readme
    assert (root / "fields.yaml").exists()
    assert len(list((root / "results").glob("*.json"))) == 5


def test_operator_readme_is_single_normal_entry_point():
    readme = Path("docs/operator/README.md").read_text(encoding="utf-8")
    root = Path("README.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(encoding="utf-8")

    assert "Normal Operator Path" in readme
    assert "reports/operator_summary.json" in readme
    assert "source-manifest" in readme
    assert "draft-source-documents" in readme
    assert "research-deck" in readme
    assert "prepare" in readme
    assert "apply" in readme
    assert "HSTuner" in readme
    assert "docs/operator/README.md" in root
    assert "docs/operator/README.md" in skill
    assert "docs/operator/README.md" in workflow


def test_normal_docs_keep_expert_paths_in_expert_sections():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    expert_index = operator.index("## Expert Paths")
    normal_index = operator.index("## Normal Operator Path")

    assert normal_index < expert_index
    for token in (
        "--cards-json",
        "--claims-json",
        "--plan-reports-dir",
        "--allow-placeholder",
    ):
        assert operator.index(token) > expert_index


def test_skill_doc_keeps_expert_paths_in_expert_section():
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")

    assert "## Expert Paths" in skill
    expert_index = skill.index("## Expert Paths")
    for token in (
        "--cards-json",
        "--claims-json",
        "--plan-reports-dir",
        "--allow-placeholder",
    ):
        assert token not in skill[:expert_index]
        assert skill.index(token) > expert_index


def test_operator_docs_explain_source_depth_closure_without_expanding_scope():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    operator_lower = operator.lower()
    negative_scope = (
        "hsconfig is pre-run only. it does not parse replays, inspect winrate, "
        "analyze runtime logs, promote candidates, or tune after games. "
        "those tasks belong to hstuner."
    )

    assert "source-depth closure" in operator_lower
    assert "docs/operator/archetype-fixture-matrix.json" in operator
    assert "close existing matrix gaps before adding more representative decks" in operator_lower

    assert negative_scope in operator_lower
    assert operator_lower.count("replay") == negative_scope.count("replay")
    assert operator_lower.count("winrate") == negative_scope.count("winrate")

    closure_sentence = (
        "every representative deck either proves `source_backed_strong` or "
        "exposes the first missing source-to-runtime link"
    )
    assert closure_sentence in skill.lower()
    assert closure_sentence in workflow.lower()
