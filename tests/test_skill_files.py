from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / "hsconfig"
ACTIVE_SKILL_REFERENCE_FILES = [
    SKILL_ROOT / "SKILL.md",
    SKILL_ROOT / "references" / "workflow.md",
    SKILL_ROOT / "references" / "visionai-surfaces.md",
    SKILL_ROOT / "references" / "contract-compiler-checklist.md",
    SKILL_ROOT / "references" / "guide-research-policy.md",
    SKILL_ROOT / "references" / "globalvalues-policy.md",
    SKILL_ROOT / "references" / "card-behavior-policy.md",
]
OLD_PRESUME_CONCEDE_NORMAL_OUTPUTS = (
    "Presume/Concede are " + "documented normal outputs"
)


def _skill_entrypoint_text() -> str:
    return (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")


def _active_skill_docs_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in ACTIVE_SKILL_REFERENCE_FILES
    )


def test_skill_has_required_files():
    expected = {
        "SKILL.md",
        "references/workflow.md",
        "references/visionai-surfaces.md",
        "references/contract-compiler-checklist.md",
        "references/guide-research-policy.md",
        "references/globalvalues-policy.md",
        "references/card-behavior-policy.md",
        "scripts/build_config.py",
        "scripts/validate_package.py",
    }

    for relative_path in expected:
        assert (SKILL_ROOT / relative_path).exists(), relative_path


def test_skill_and_workflow_stay_compact_and_canonical():
    skill = _skill_entrypoint_text()
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
    checklist = (SKILL_ROOT / "references" / "contract-compiler-checklist.md").read_text(
        encoding="utf-8"
    )
    active_docs = _active_skill_docs_text()
    combined = f"{skill}\n{workflow}"

    assert skill.count("\n") < 80
    assert workflow.count("\n") < 120
    for phrase in [
        "docs/operator/README.md",
        "Preferred normal path: `hsconfig configure`.",
        "`reports/operator_summary.json` remains the only normal apply authority.",
    ]:
        assert phrase in skill
    for text in (workflow, active_docs):
        assert "hsconfig configure" in text
        assert "reports/operator_summary.json" in text
        assert "VALID_PACKAGE" in text
        assert "load_safe_apply" in text
    assert "HSConfig is pre-run only" in combined
    assert "does not parse replays" in combined
    reference_section = skill.split("## References:", 1)[1]
    assert "references/contract-compiler-checklist.md" in reference_section
    assert "Contract compiler checklist: `references/contract-compiler-checklist.md`." in skill
    assert "Contract compiler checklist: `references/contract-compiler-checklist.md`." in workflow
    assert "reports/operator_summary.json" in checklist
    assert "SOURCE_BACKED_STRONG" in checklist
    assert "default_only_runtime_surfaces=[]" in checklist
    assert "Darkbishop gate" in checklist
    assert "`GlobalValues.json`" in combined
    assert "`Mulligan.json`" in combined
    assert "per-card" in combined
    assert "<CARDID>.json" in combined
    assert "`Combo.json`" in combined
    assert (
        "`Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are "
        "legacy/diagnostic VisionAI surfaces outside the normal HSConfig output "
        "path. Their absence never blocks a valid load-safe package, and their "
        "presence in a normal package is treated as drift."
    ) in active_docs
    for duplicate_section in [
        "Preferred normal workflow:",
        "Lower-level inspected workflow:",
        "Status meaning:",
        "Fixture stage meaning:",
        "## Research Normalization",
        "## Package Preparation",
        "## Readiness Interpretation",
        "## Fixture Stage Semantics",
        "## Diagnostic And Expert Paths",
        "Current closure truth is",
    ]:
        assert duplicate_section not in combined


def test_active_docs_document_presume_aoe_surface_without_normal_output():
    active_files = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        SKILL_ROOT / "references" / "workflow.md",
        SKILL_ROOT / "references" / "visionai-surfaces.md",
    ]
    active_docs = "\n".join(path.read_text(encoding="utf-8") for path in active_files)
    required = [
        "`Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are "
        "legacy/diagnostic VisionAI surfaces outside the normal HSConfig output "
        "path. Their absence never blocks a valid load-safe package, and their "
        "presence in a normal package is treated as drift.",
    ]
    forbidden = [
        "without a current verified first-party help-page citation",
        "does not currently verify a current first-party help-page citation",
        "lacks a current verified first-party help-page citation",
        OLD_PRESUME_CONCEDE_NORMAL_OUTPUTS,
    ]

    for phrase in required:
        assert phrase in active_docs, phrase
    for path in active_files + [SKILL_ROOT / "SKILL.md"]:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, f"{path}: {phrase}"


def test_active_docs_call_presume_concede_legacy_diagnostic_not_normal_path():
    active_paths = [
        REPO_ROOT / ".agents" / "skills" / "hsconfig" / "references" / "workflow.md",
        REPO_ROOT / ".agents" / "skills" / "hsconfig" / "references" / "visionai-surfaces.md",
        REPO_ROOT / "docs" / "operator" / "README.md",
        REPO_ROOT / "docs" / "operator" / "universal-wild-no-block-contract.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)

    required_sentence = (
        "`Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are "
        "legacy/diagnostic VisionAI surfaces outside the normal HSConfig output "
        "path. Their absence never blocks a valid load-safe package, and their "
        "presence in a normal package is treated as drift."
    )
    assert required_sentence in combined

    forbidden_phrases = [
        "`Concede.json` is publicly documented",
        "`Presume.json` is publicly documented",
        "normal HSConfig does not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`; absence",
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined


def test_skill_content_sets_direct_config_boundary():
    text = _skill_entrypoint_text()
    entrypoint_required = [
        "name: hsconfig",
        "HearthRanger",
        "HSConfig is pre-run only.",
        "Preferred normal path: `hsconfig configure`.",
        "`reports/operator_summary.json` remains the only normal apply authority.",
        "`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply gate.",
        "`source_status_apply_blocking` must remain `false` for source-quality work.",
        "Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning.",
        "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.",
        "Runtime apply is guarded",
        "Effect semantics are not opening-hand mulligan keeps.",
        "Card-intent taxonomy is diagnostic-only.",
        "## References:",
        "Contract compiler checklist: `references/contract-compiler-checklist.md`.",
    ]

    for phrase in entrypoint_required:
        assert phrase in text
    assert "per-card" in text
    assert "<CARDID>.json" in text


def test_active_skill_docs_keep_detailed_policy_vocabulary():
    text = _active_skill_docs_text()
    active_docs_required = [
        "source_closure_intake_receipt.json",
        "latest_research_result_contract_first_non_promoting_*",
        "source claim -> normalized `claim_kind` -> semantic qualifiers",
        "mechanic lowering registry",
        "warning_boundaries",
        "globalvalue_numeric_tuning",
        "per_card_config_readiness_report.json",
        "source_to_runtime_explainability.json",
        "source_evidence_closure.json",
    ]

    for phrase in active_docs_required:
        assert phrase in text


def test_skill_names_configure_normal_workflow():
    text = _skill_entrypoint_text()
    active_docs = _active_skill_docs_text()

    assert "Normal workflow:" in text
    assert "1. Prefer `hsconfig configure ...` for normal operation." in text
    assert (
        "2. Use lower-level commands only when inspecting a stage:\n"
        "   `source-manifest -> source-autopilot or draft-source-documents -> "
        "research-deck -> prepare -> validate -> apply`."
    ) in text
    assert (
        "3. After `configure`, read "
        "`<out>/configure_summary.json.acceptance_summary` first; use "
        "`reports/operator_summary.json` as the apply authority."
    ) in text
    assert "`hsconfig configure --auto-source --source-search-results-json ...`" in active_docs
    assert "`source-autopilot` is source-strength preflight, not runtime apply authority." in active_docs


def test_skill_and_workflow_show_complete_fresh_configure_command() -> None:
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(
        encoding="utf-8"
    )
    expected_command = (
        'hsconfig configure --deck-name "<DeckName>" '
        '--deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" '
        '--out "outputs/<DeckName>" --online-source --auto-source --apply --json'
    )
    incomplete_command = (
        'hsconfig configure --deck-name "<DeckName>" '
        '--deck-code "<DeckCode>" --online-source --auto-source --apply'
    )

    for text in (skill, workflow):
        assert expected_command in text
        assert incomplete_command not in text


def test_docs_and_skill_keep_config_quality_summary_diagnostic_only():
    operator_docs = (REPO_ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )
    active_docs = _active_skill_docs_text()

    operator_fragment = operator_docs.split("## Optional Contract Doctor", 1)[1].split(
        "## Expert Paths", 1
    )[0]
    combined = f"{operator_fragment}\n{active_docs}"

    assert "<out>/configure_summary.json.acceptance_summary" in combined
    assert "acceptance_summary" in combined
    assert "use_config_now" in combined
    assert "next_report_to_open" in combined
    assert "<out>/configure_summary.json.config_quality_summary" in combined
    assert "config_quality_summary" in combined
    assert "<out>/configure_summary.json.config_proof_summary" in combined
    assert "diagnostic-only config proof" in combined
    assert "not another apply gate" in combined
    assert "does not replace `reports/operator_summary.json`" in combined
    assert "diagnostic-only" in combined
    assert "non-blocking" in combined
    assert "contract-doctor" in combined
    assert "operator_summary.json" in combined
    assert "normal apply authority" in combined


def test_docs_skill_and_workflow_route_configure_acceptance_summary_first() -> None:
    operator_docs = (REPO_ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = f"{operator_docs}\n{_active_skill_docs_text()}"

    assert "<out>/configure_summary.json.acceptance_summary" in combined
    assert "use_config_now" in combined
    assert "next_report_to_open" in combined
    assert "operator projection" in combined
    assert "operator_summary.json" in combined
    assert "apply authority" in combined


def test_skill_names_source_closure_intake_receipt_without_new_authority():
    text = _active_skill_docs_text()

    assert "source_closure_intake_receipt.json" in text
    assert "source_closure_intake" in text
    assert "acquisition input" in text
    assert "cannot promote, block, write runtime config" in text
    assert "replace `operator_summary.json`" in text


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
        SKILL_ROOT / "references" / "workflow.md",
    ]
    active_docs = "\n".join(path.read_text(encoding="utf-8") for path in operator_path_files)
    required_terms = {
        "source_documents.json",
        "source-autopilot",
        "--auto-source",
        "02_source_autopilot",
        "hsconfig research-deck --source-documents-json",
        "hsconfig prepare --guide-sources-json",
        "operator_summary.json",
        "hsconfig apply",
    }

    assert "docs/operator/README.md" in root_readme
    assert "Preferred normal path: `hsconfig configure`" in root_readme
    assert "Lower-level inspected path:" in root_readme
    assert "hsconfig source-manifest" in root_readme
    assert "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`." in root_readme

    for path in operator_path_files:
        text = path.read_text(encoding="utf-8")
        assert "Preferred normal path: `hsconfig configure`" in text
        assert "Lower-level inspected path:" in text
    assert "Preferred normal path: `hsconfig configure`" in _skill_entrypoint_text()
    assert "Lower-level inspected path:" in _skill_entrypoint_text()
    for term in required_terms:
        assert term in active_docs


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


def test_skill_source_policy_documents_evergreen_wild_closure_boundary():
    skill_policy = (SKILL_ROOT / "references" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    active_docs = _active_skill_docs_text()
    required_terms = [
        "evergreen_wild_archetype",
        "SOURCE_BACKED_STRONG",
        "full-text public Wild guide",
        "explicit card overlap",
        "old non-Wild guides",
        "snippets",
        "decklists",
        "HSReplay/HSGuru aggregate stats",
        "static card databases",
        "hero_power_transform",
        "must not prove strategic runtime surfaces by themselves",
        "must not create opening-hand Mulligan keeps without an explicit mulligan claim",
        "operator_summary.json remains the only normal apply authority",
    ]

    for term in required_terms:
        assert term in active_docs
        assert term in skill_policy or term in active_docs


def test_skill_documents_guide_depth_closure_reports():
    skill = _skill_entrypoint_text()
    active_docs = _active_skill_docs_text()

    assert "per_card_config_readiness_report.json" in active_docs
    assert "guide_source_depth_report.json" in active_docs
    assert "no replay analysis" in skill.lower()
    assert "winrate" in skill.lower()


def test_skill_workflow_documents_deckstring_default_and_runtime_mapping():
    text = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")

    assert "HearthSim deckstring decode" in text
    assert "deckstring_decode_receipt.json" in text
    assert "fake apply" in text.lower()
    assert "card_id_map.json" in text
    assert "CustomConfig/deck_config.ini" in text
    assert "--allow-placeholder" in text
    assert "hsconfig prepare" in text
    assert "research-deck" in text
    assert "research-contract" in text
    assert "reports/research" in text
    assert "--guide-sources-json" in text


def test_skill_docs_keep_presume_concede_out_of_normal_path():
    active_files = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
        Path(".agents/skills/hsconfig/references/visionai-surfaces.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_files)
    required_terms = [
        "Concede.json",
        "Presume.json",
        "legacy/diagnostic VisionAI surfaces",
        "normal HSConfig",
        "outside the normal HSConfig output path",
    ]

    for term in required_terms:
        assert term in combined, term
    assert "Presume.json" in _skill_entrypoint_text()
    assert "Concede.json" in _skill_entrypoint_text()


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


def test_skill_docs_use_per_card_cardid_json_wording():
    docs = {
        "docs/operator/README.md": "`per-card <CARDID>.json`",
        ".agents/skills/hsconfig/SKILL.md": "per-card `<CARDID>.json`",
        ".agents/skills/hsconfig/references/workflow.md": "`per-card <CARDID>.json`",
        ".agents/skills/hsconfig/references/card-behavior-policy.md": "`per-card <CARDID>.json`",
        ".agents/skills/hsconfig/references/visionai-surfaces.md": "`per-card <CARDID>.json`",
    }

    for relative_path, phrase in docs.items():
        text = Path(relative_path).read_text(encoding="utf-8")
        assert phrase in text


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


def test_skill_sources_document_runtime_apply_mode_as_descriptive():
    skill = _skill_entrypoint_text()
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
    operator = (REPO_ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = f"{workflow}\n{operator}"

    assert "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`." in skill
    assert "Runtime apply is guarded" in skill
    assert "receipt.runtime_package_match.status" in skill
    assert "This is an install-integrity check, not a source/semantic apply gate." in skill
    assert "runtime_apply_mode" in combined
    assert "runtime_apply_allowed" in combined
    assert "ALLOWED_WITH_WARNINGS" in combined
    assert "ALLOWED_WITH_WARNINGS as runtime write permission" not in combined

    assert "runtime_apply_mode" in workflow
    assert "human-readable write mode" in workflow
    assert "hsconfig apply" in workflow
    assert "apply_package()" in workflow
    assert "re-evaluate the operator gate before writing" in workflow
    assert "receipt.runtime_package_match.status" in workflow
    assert "runtime-match --package <package> --runtime-root <runtime> --json" in workflow
    assert "This is an install-integrity check, not a source/semantic apply gate." in workflow


def test_readme_documents_installed_skill_sync():
    text = Path("README.md").read_text(encoding="utf-8")
    normalized = text.replace("\\", "/")

    assert "scripts/sync_installed_skill.py --check" in normalized
    assert "scripts/sync_installed_skill.py" in normalized


def test_docs_make_operator_summary_the_single_normal_gate():
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            _active_skill_docs_text(),
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
        ]
    )

    assert docs.count("operator_summary.json") >= 3
    assert "single operator gate" in docs.lower()
    assert "replay" in docs.lower()
    assert "does not parse replays" in docs


def test_docs_and_skill_explain_contract_conformance_snapshot():
    combined = (
        Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/references/workflow.md").read_text(
            encoding="utf-8"
        )
    )

    assert "contract conformance snapshot" in combined.lower()
    assert "documentation-as-code" in combined
    assert "does not create a second operator apply path" in combined
    assert "operator_summary.json remains the normal apply authority" in combined


def test_docs_explain_contract_spine_without_new_apply_gate():
    owning_paths = [
        REPO_ROOT / ".agents" / "skills" / "hsconfig" / "references" / "workflow.md",
        REPO_ROOT / "docs" / "operator" / "guide-research-policy.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in owning_paths)
    required_paragraph = (
        "`contract_spine_rows` are diagnostic. They provide the compact "
        "source -> policy -> surface gate -> builder/router -> runtime effect "
        "chain for each claim kind. They do not grant apply permission, and "
        "operator_summary.json remains the normal apply authority."
    )

    assert "contract_spine_rows" in combined
    assert "source -> policy -> surface gate -> builder/router -> runtime effect" in combined
    assert "operator_summary.json remains the normal apply authority" in combined
    for path in owning_paths:
        text = path.read_text(encoding="utf-8")
        assert required_paragraph in text, path
        assert text.count(required_paragraph) == 1, path
    assert ("contract_spine_rows are an " + "apply gate") not in combined


def test_docs_and_skill_distinguish_contract_drift_from_builder_prerequisites():
    combined = (
        Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/references/workflow.md").read_text(
            encoding="utf-8"
        )
    )

    assert "unexpected contract drift" in combined.lower()
    assert "builder prerequisite gap" in combined.lower()
    assert "no-block package generation" in combined.lower()
    assert "operator_summary.json remains the normal apply authority" in combined


def test_docs_do_not_advertise_presume_concede_as_normal_outputs():
    active_docs = [
        Path("README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    forbidden = [
        "emit Presume.json",
        "emit Concede.json",
        "normal output includes " + "Presume",
        "normal output includes " + "Concede",
    ]
    for path in active_docs:
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text


def test_skill_docs_explain_strong_fixture_truth_contract():
    docs = "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            _active_skill_docs_text(),
            Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8"),
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


def test_skill_docs_explain_load_safe_apply_mode():
    skill = _skill_entrypoint_text()
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(encoding="utf-8")
    operator = (REPO_ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )
    combined = f"{workflow}\n{operator}"

    assert "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`." in skill
    assert "runtime_load_safe" in combined
    assert "load_safe_apply" in combined
    assert (
        "ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE"
        in combined
    )
    assert "technical_status=VALID_PACKAGE" in workflow
    assert "runtime_load_safe=true" in workflow
    assert "runtime_apply_mode=load_safe_apply" in workflow
    assert "blocks by default unless the package is source-backed ready" not in workflow.lower()
    assert "source-backed ready" not in workflow.lower()


def test_skill_docs_distinguish_rich_output_from_minimal_apply_gate():
    docs = "\n".join(
        [
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(
                encoding="utf-8"
            ),
            Path(".agents/skills/hsconfig/references/card-behavior-policy.md").read_text(
                encoding="utf-8"
            ),
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
        ]
    )

    normalized_docs = " ".join(docs.split())

    assert "HSConfig rich-output repo policy" in docs
    assert "not the minimal runtime-write gate" in normalized_docs
    assert "not an official HearthRanger minimum" in normalized_docs
    assert "`load_safe_apply` is an HSConfig operator policy" in docs


def test_skill_docs_mark_repo_supported_source_gap_blocks():
    card_policy = Path(
        ".agents/skills/hsconfig/references/card-behavior-policy.md"
    ).read_text(encoding="utf-8")

    for block in ["OnAdaptCardBonus", "BeforeUpgradeCardBonus", "OnBoardPlayPriority"]:
        assert block in card_policy
    assert "repo-supported source-gap blocks" in card_policy
    assert "not confirmed in the latest public-doc audit" in card_policy


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
    skill = _skill_entrypoint_text()

    assert "## Expert Paths" in skill
    expert_index = skill.index("## Expert Paths")
    expert_skill = skill[expert_index:]

    assert "hsconfig contract-preflight --json" in expert_skill
    assert "--skill-install-root" in expert_skill
    assert "--skill-install-root" not in skill[:expert_index]
    assert "--allow-placeholder" in expert_skill


def test_operator_docs_explain_source_depth_closure_without_expanding_scope():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    active_docs = _active_skill_docs_text()
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    operator_lower = operator.lower()
    active_docs_lower = active_docs.lower()
    workflow_lower = workflow.lower()
    negative_scope = (
        "hsconfig is pre-run only. it does not parse replays, inspect winrate, "
        "analyze runtime logs, promote candidates, or tune after games. "
        "those tasks belong to hstuner."
    )
    second_clause = "close existing matrix gaps before adding more representative decks"

    assert "source-depth closure" in operator_lower
    assert "docs/operator/archetype-fixture-matrix.json" in operator
    assert second_clause in operator_lower

    assert negative_scope in operator_lower
    assert operator_lower.count("replay") == negative_scope.count("replay")
    assert operator_lower.count("winrate") == negative_scope.count("winrate")

    closure_sentence = (
        "every representative deck either proves `source_backed_strong` or "
        "exposes the first missing source-to-runtime link"
    )
    assert closure_sentence in active_docs_lower
    assert second_clause in active_docs_lower
    assert closure_sentence in workflow_lower
    assert second_clause in workflow_lower


def test_docs_explain_source_informed_apply_ready_lane():
    docs = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8"),
            Path(".agents/skills/hsconfig/references/workflow.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "runtime_load_safe" in docs
    assert "load_safe_apply" in docs
    assert (
        "ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE"
        in docs
    )
    assert "ALLOWED_SOURCE_INFORMED" not in docs
    assert "--allow-source-informed --json" not in docs


def test_skill_names_preserved_closure_rows_and_no_actionable_target():
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    active_docs = _active_skill_docs_text()

    expected = (
        "After durable Boarlock and Kingslayer preservation, the current actionable "
        "source-informed closure targets are CtAPaladin, Discolock, TreantDruid, and PirateDH."
    )
    assert expected in active_docs
    assert expected in workflow


def test_docs_explain_config_usefulness_without_making_it_a_blocker():
    operator_readme = Path("docs/operator/README.md").read_text(encoding="utf-8")
    no_block_contract = Path("docs/operator/universal-wild-no-block-contract.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([operator_readme, no_block_contract, _active_skill_docs_text()])

    assert "config_usefulness" in combined
    assert "load-safe" in combined
    assert "non-blocking" in combined
    assert "load_safe_but_thin" in combined
    assert "usable_with_targeted_gaps" in combined
    assert "next_report_to_open" in combined
    assert "HSTuner" in combined
    assert "does not parse replays" in operator_readme
    assert operator_readme.lower().count("replay") == 1


def test_docs_and_skill_explain_mechanic_visibility_without_blocking_apply():
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "mechanic_visibility_summary" in combined
    assert "identity_gated_direct" in combined
    assert "warning-only mechanics are descriptive" in combined
    assert "must not block load-safe apply" in combined


def test_docs_and_skill_explain_mechanic_lowering_registry_authority():
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "mechanic lowering registry" in combined.lower()
    assert "cards_needing_mechanic_lowering" in combined
    assert "needs_mechanic_lowering" in combined
    assert "documented default CardID lowering target" in combined
    assert "Dredge, Tradeable, and unknown future mechanics" in combined
    assert "do not increment `cards_needing_mechanic_lowering`" in combined


def test_docs_and_skill_explain_current_modern_mechanic_visibility_without_blocking():
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for mechanic in [
        "`kindred`",
        "`tourist`",
        "`starship`",
        "`spellburst`",
        "`miniaturize`",
        "`quickdraw`",
        "`honorable_kill`",
        "`elusive`",
        "`poisonous`",
        "`imbue`",
        "`rewind`",
        "`herald`",
        "`shatter`",
    ]:
        assert mechanic in combined

    assert "modern mechanic visibility is non-blocking" in combined.lower()
    assert "reports/mechanic_drift_report.json" in combined
    assert "reports/semantic_enrichment_report.json" in combined
    assert "source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply" in combined


def test_new_modern_mechanics_are_report_only_visibility_not_partial_lowering():
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    mechanics = ["`rewind`", "`herald`", "`shatter`"]
    visibility_terms = ("report-only", "warning-only", "warning_only")

    for path in paths:
        text = path.read_text(encoding="utf-8")
        mechanic_lines = [
            line.strip()
            for line in text.splitlines()
            if any(mechanic in line for mechanic in mechanics)
        ]

        assert mechanic_lines, f"{path}: missing explicit new mechanic wording"
        mechanic_context = "\n".join(mechanic_lines).lower()
        for mechanic in mechanics:
            assert mechanic in text, f"{path}: {mechanic}"
        assert any(term in mechanic_context for term in visibility_terms), path
        assert "partial" not in mechanic_context, path
        assert "lower" not in mechanic_context, path


def test_universal_wild_contract_keeps_generated_entity_partial():
    text = Path("docs/operator/universal-wild-no-block-contract.md").read_text(
        encoding="utf-8"
    )

    assert "exact option or transformed-identity resolution" in text
    assert "`generated_entity` and its `spell_generation` alias stay in `partial`" in text
    assert "generated-card" not in text


def test_docs_and_skill_explain_visibility_only_mechanic_polish():
    paths = [
        Path("docs/operator/universal-wild-no-block-contract.md"),
        Path("docs/operator/README.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
        Path(".agents/skills/hsconfig/references/card-behavior-policy.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "`choose_one`" in combined
    assert "`board_position`" in combined
    assert "`generic_spell_target`" in combined
    assert "`location_activation`" in combined
    assert "`secret_timing`" in combined
    assert "`generated_entity_random_pool`" in combined
    assert "first_warning_boundary" in combined
    assert "warning_boundaries" in combined
    assert "first next-inspection item" in combined
    assert "complete alphabetical list" in combined
    assert "must not block load-safe apply" in combined
    assert "`generated_entity` and its `spell_generation` alias stay in `partial`" in combined
    assert "Current warning-only mechanics" not in combined


def test_skill_docs_explain_mechanic_drift_is_nonblocking():
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    combined = f"{skill}\n{workflow}"
    assert "mechanic_drift_summary" in combined
    assert "reports/mechanic_drift_report.json" in combined
    assert "Unknown mechanics are warning-only and do not block load-safe apply" in combined


def test_skill_explains_no_block_failure_mode_summary():
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    combined = f"{skill}\n{workflow}"

    assert "no_block_failure_mode_summary" in combined
    assert "technical_hard_block" in combined
    assert "warning_only_mechanic" in combined
    assert "future_mechanic_drift" in combined
    assert "does not create a second apply path" in combined


def test_skill_explains_source_contract_audit_without_new_gate():
    skill = _skill_entrypoint_text()
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    combined = f"{skill}\n{workflow}"

    assert "reports/source_contract_audit.json" in combined
    assert "reports/source_to_runtime_explainability.json" in combined
    assert "reports/source_evidence_closure.json" in combined
    assert "source_contract_audit_summary" in combined
    assert "source_to_runtime_explainability_summary" in combined
    assert "source_evidence_closure_summary" in combined
    assert "do not replace `reports/operator_summary.json`" in skill
    assert "does not create a second apply path" in combined
    assert "claim_lifecycle_rows" in combined
    assert "policy_lane" in combined
    assert "source -> policy -> surface gate -> builder/router -> emitted/suppressed" in combined
    assert "runtime emission" in combined


def test_source_contract_lifecycle_docs_keep_operator_summary_authority():
    operator_policy = Path("docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    active_docs = _active_skill_docs_text()
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/guide-research-policy.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    combined_lower = combined.lower()

    assert "claim_lifecycle_rows" in combined
    assert "operator_summary.json" in combined
    assert "diagnostic" in combined_lower
    assert "policy_lane" in combined
    assert "source -> policy -> surface gate -> builder/router -> emitted/suppressed" in combined
    assert "source_contract_audit.json` is diagnostic" in combined
    assert "audit is an apply gate" not in combined_lower
    assert (
        "source_contract_audit.json remains the normal apply " + "authority"
    ) not in combined

    assert "### Claim Lifecycle End States" in operator_policy
    assert "`source_contract_audit.json.claim_lifecycle_rows` is diagnostic-only" in operator_policy
    for state in ("`emitted`", "`suppressed`", "`not_seen_by_builder`"):
        assert state in operator_policy
    assert "implementation debt, not an operator" in operator_policy
    assert "Do not use\n`source_contract_audit.json` as an apply gate." in operator_policy

    assert "technically valid" in active_docs
    assert "low confidence" in active_docs
    assert "report-only" in active_docs
    assert "runtime surface" in active_docs
    assert "source_contract_audit.json" in active_docs


def test_docs_and_skill_state_source_contract_invariant_rule():
    docs = (
        Path("docs/operator/README.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
        + "\n"
        + Path(".agents/skills/hsconfig/references/workflow.md").read_text(
            encoding="utf-8"
        )
    )
    normalized = docs.replace("`", "")

    assert "effect semantics are preserved" in normalized
    assert "only exact runtime-surface claims lower" in normalized
    assert "source_contract_audit.json is diagnostic" in normalized
    assert "operator_summary.json remains the normal apply authority" in normalized


def test_docs_and_skill_describe_contract_doctor_as_diagnostic_only():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    skill = Path(".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([operator, skill, workflow])

    assert "hsconfig contract-doctor" in combined
    assert "diagnostic" in combined.lower()
    assert "operator_summary.json remains the only normal apply authority" in combined
    assert "contract-doctor is an apply gate" not in combined


def test_docs_explain_apply_authority_and_diagnostic_chain_in_one_place():
    paths = [
        Path("docs/operator/README.md"),
        Path("docs/operator/guide-research-policy.md"),
        Path(".agents/skills/hsconfig/SKILL.md"),
        Path(".agents/skills/hsconfig/references/workflow.md"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "`operator_summary.json` remains the only normal apply authority." in combined
    assert "`source_contract_audit.json` explains why each claim did or did not lower." in combined
    assert "`source_to_runtime_explainability.json` is the card-readable diagnostic projection" in combined
    assert "`source_evidence_closure.json` is the compact diagnostic package-quality closure summary" in combined
    assert "`contract_spine_rows` show the compact source -> policy -> surface gate -> builder/router -> runtime effect chain." in combined
    assert "Warnings are follow-up work, not a runtime apply blocker." in combined
    assert "Do not use `source_contract_audit.json` as an apply gate." in combined


def test_docs_describe_source_quality_as_non_blocking():
    docs = (
        Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")
        + "\n"
        + _active_skill_docs_text()
    )

    assert "source_claim_quality_summary" in docs
    assert "source_evidence_closure.json" in docs
    assert "non-blocking" in docs.lower()
    assert "operator_summary.json" in docs
    assert "source_contract_audit.json" in docs
    assert "second apply path" in docs.lower()


def test_hsconfig_skill_explains_start_effect_mulligan_split():
    text = _skill_entrypoint_text()

    assert "Effect semantics are not opening-hand mulligan keeps" in text
    assert "Darkbishop Benedictus" in text
    assert "remains the only normal apply authority" in text


def test_hsconfig_skill_documents_source_closure_optimizer_boundary() -> None:
    workflow = Path(".agents/skills/hsconfig/references/workflow.md").read_text(
        encoding="utf-8"
    )

    assert "source-closure-optimizer" in workflow
    assert "diagnostic" in workflow.lower()
    assert "does not replace `reports/operator_summary.json`" in workflow


def test_docs_and_skill_explain_contract_invariant_closure_without_new_gate():
    operator_docs = Path("docs/operator/README.md").read_text(encoding="utf-8")
    active_docs = _active_skill_docs_text()
    combined = operator_docs + "\n" + active_docs

    required = (
        "Contract invariant closure means: single apply authority, no silent "
        "default-only success, claim-kind surface discipline, and effect-not-mulligan "
        "canary coverage. It is diagnostic proof, not another runtime apply gate."
    )

    assert required in operator_docs
    assert "another runtime apply gate" in combined
    assert "operator_summary.json remains the only normal apply authority" in combined


def test_docs_and_skill_route_installed_skill_sync_through_contract_preflight():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    skill = _skill_entrypoint_text()
    combined = f"{operator}\n{skill}"
    skill_lines = skill.splitlines()
    expert_headings = [
        line for line in skill_lines if line.startswith("## Expert Paths")
    ]
    assert expert_headings == ["## Expert Paths"]
    expert_index = skill_lines.index("## Expert Paths")

    pre_expert_skill = "\n".join(skill_lines[:expert_index])
    expert_skill = "\n".join(skill_lines[expert_index:])
    preflight_marker = "Use `hsconfig contract-preflight --json`"
    operator_preflight = (
        preflight_marker + operator.split(preflight_marker, 1)[1].split("\n\n", 1)[0]
    )
    operator_preflight_flat = " ".join(operator_preflight.split())

    assert "installed-skill sync" in operator
    assert "hsconfig contract-preflight --json" in combined
    assert "--skill-install-root" in operator
    assert "diagnostic-only" in combined
    assert "hsconfig contract-preflight --json" in expert_skill
    assert "installed-skill sync" not in pre_expert_skill
    assert "--skill-install-root" not in pre_expert_skill
    assert "`hsconfig contract-preflight --json`" in operator_preflight
    assert "--skill-install-root" in operator_preflight
    assert "diagnostic-only" in operator_preflight
    assert "preflight is diagnostic-only" in operator_preflight_flat
    assert "default-only success" not in operator_preflight_flat.lower()
    assert "default-only success" not in expert_skill.lower()


def test_skill_and_workflow_describe_card_intent_taxonomy_as_diagnostic_only():
    skill = _skill_entrypoint_text()
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(
        encoding="utf-8"
    )
    expected = (
        "Card-intent taxonomy is diagnostic-only; it explains per-card config "
        "signals but does not encode HearthRanger gameplay sequencing or create "
        "another apply gate."
    )

    assert "Card-intent taxonomy is diagnostic-only" in skill
    assert "does not encode HearthRanger gameplay sequencing" in skill
    assert expected in workflow


def test_hsconfig_skill_keeps_explicit_no_hstuner_after_game_boundary():
    skill = _skill_entrypoint_text()

    assert (
        "Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning."
        in skill
    )
    assert "Card-intent taxonomy is diagnostic-only" in skill
    assert "does not encode HearthRanger gameplay sequencing" in skill


def test_hsconfig_skill_mentions_handoff_contract_and_research_sentinel() -> None:
    text = _skill_entrypoint_text()
    active_docs_and_operator = (
        _active_skill_docs_text()
        + "\n"
        + Path("docs/operator/README.md").read_text(encoding="utf-8")
    )

    assert "configure_summary.json.handoff_contract" in text
    assert "research-result sentinel" in active_docs_and_operator
    assert "diagnostic-only" in text
    assert "remains the only normal apply authority" in text


def test_skill_and_operator_docs_name_pre_run_config_contract_receipt() -> None:
    active_paths = [
        REPO_ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "workflow.md",
        REPO_ROOT / "docs" / "operator" / "README.md",
    ]

    required = [
        "pre-run config contract receipt",
        "configure_summary.json.handoff_contract",
        "diagnostic-only handoff proof",
        "single authority",
        "no-default-only status",
        "Darkbishop boundary",
        "does not replace `reports/operator_summary.json`",
    ]

    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)
    assert "configure_summary.json.handoff_contract" in _skill_entrypoint_text()
    for phrase in required:
        assert phrase in combined, phrase


def test_skill_and_operator_docs_explain_research_deep_contract_bridge() -> None:
    paths = [
        REPO_ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "workflow.md",
        REPO_ROOT / "docs" / "operator" / "README.md",
    ]
    required = [
        "latest_research_result_contract_first_non_promoting_*",
        "first source action needed for Strong closure",
        "diagnostic-only",
        "cannot block or promote a package",
        "operator_summary.json remains the only normal apply authority",
    ]

    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for phrase in required:
        assert phrase in combined, phrase
