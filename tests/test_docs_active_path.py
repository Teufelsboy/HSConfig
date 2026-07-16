from pathlib import Path


OLD_LOWER_LEVEL_LABEL = "Lower-level " + "normal path:"
OLD_LOWER_LEVEL_SENTENCE = (
    "The lower-level " + "normal path remains available for inspected work:"
)
OLD_RUNTIME_WRITE_SENTENCE = (
    "Runtime writes remain only when requested through `hsconfig " + "apply`."
)


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


def test_operator_docs_name_configure_as_preferred_normal_path():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "## Preferred Normal Path" in text
    assert "Use `hsconfig configure` for normal operation:" in text
    assert (
        'hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" '
        '--runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --json'
    ) in text
    assert (
        "This command runs the lower-level pre-run chain, writes a validated "
        "package, and leaves the final decision in "
        "`outputs/<DeckName>/04_package/reports/operator_summary.json`."
    ) in text
    assert "For staged inspection, use the Lower-Level Inspected Path below." in text
    assert (
        "source-manifest -> draft-source-documents -> research-deck -> "
        "prepare -> validate -> apply"
    ) in text
    assert "HSConfig is pre-run only" in text


def test_preferred_path_docs_use_single_lower_level_chain_label():
    exact_chain = (
        "source-manifest -> draft-source-documents -> research-deck -> "
        "prepare -> validate -> apply"
    )
    root_readme = Path("README.md").read_text(encoding="utf-8")
    operator_readme = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert root_readme.count(exact_chain) == 1
    assert operator_readme.count(exact_chain) == 1
    assert "Lower-level inspected path:" in root_readme
    assert "## Lower-Level Inspected Path" in operator_readme
    assert OLD_LOWER_LEVEL_LABEL not in root_readme
    assert OLD_LOWER_LEVEL_LABEL not in operator_readme
    assert OLD_LOWER_LEVEL_SENTENCE not in root_readme
    assert OLD_LOWER_LEVEL_SENTENCE not in operator_readme


def test_runtime_write_wording_names_apply_and_configure_apply():
    root_readme = Path("README.md").read_text(encoding="utf-8")
    operator_readme = Path("docs/operator/README.md").read_text(encoding="utf-8")

    expected = "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`."
    assert expected in root_readme
    assert expected in operator_readme
    assert OLD_RUNTIME_WRITE_SENTENCE not in root_readme


def test_operator_docs_keep_source_backed_strong_out_of_apply_permission():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert (
        "`semantic_status=SOURCE_BACKED_STRONG` means source coverage and "
        "per-card closure support source-backed confidence and handoff."
    ) in text
    assert (
        "`semantic_status=SOURCE_BACKED_STRONG` means source coverage and "
        "per-card closure are strong enough for normal apply or handoff."
    ) not in text
    assert (
        "`runtime_apply_mode=load_safe_apply` means normal `hsconfig apply --json` "
        "is allowed."
    ) in text


def test_operator_docs_explain_runtime_apply_mode_is_descriptive():
    operator_docs = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "runtime_load_safe" in operator_docs
    assert "load_safe_apply" in operator_docs
    assert (
        "ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE"
        in operator_docs
    )
    assert "ALLOWED_WITH_WARNINGS is not runtime write permission" not in operator_docs


def test_universal_no_block_contract_labels_per_card_every_card_as_rich_policy():
    text = Path("docs/operator/universal-wild-no-block-contract.md").read_text(
        encoding="utf-8"
    )

    assert "HSConfig rich-output repo policy" in text
    assert "not the minimal runtime-apply gate" in text
    assert "not an official HearthRanger minimum" in text
    assert "one per-card JSON file for every unique deck CardID" in text


def test_universal_no_block_contract_documents_card_data_intake_layers():
    text = Path("docs/operator/universal-wild-no-block-contract.md").read_text(
        encoding="utf-8"
    )

    assert "## Card Data Intake" in text
    assert "HSConfig uses a three-layer intake policy:" in text
    assert (
        "Layer 1: deck-card identity is gated through collectible deck-card metadata."
        in text
    )
    assert (
        "Layer 2: directly referenced companion entities are enriched from full "
        "`cards.json` metadata when available."
    ) in text
    assert (
        "Layer 3: text-only or rule-only mechanics stay visible in mechanic-drift "
        "reports."
    ) in text
    assert (
        "Layer 2 and Layer 3 gaps are warning-only. They must not block "
        "`load_safe_apply` when the package is otherwise `VALID_PACKAGE`."
    ) in text


def test_source_backed_closure_uses_promotion_blocker_language():
    text = Path("docs/operator/source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )

    assert "Promotion blocker reason" in text
    assert "Hard blocker reason" not in text
    assert "runtime apply is no longer blocked by source strength" in text


def test_docs_define_source_backed_strong_without_second_gate():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "operator" / "source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )

    assert "SOURCE_BACKED_STRONG is an evidence-quality label" in text
    assert "operator_summary.json remains the only normal apply authority" in text
    assert "valid load-safe config" in text
    assert "default-only" in text


def test_operator_docs_define_closure_diagnostics_as_summaries_not_gates():
    closure = Path("docs/operator/source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )
    workflow = Path("docs/operator/source-builder-workflow.md").read_text(
        encoding="utf-8"
    )
    policy = Path("docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([closure, workflow, policy])

    assert "source_backed_strong_closure" in combined
    assert "no_default_only_runtime_status" in combined
    assert (
        "`source_backed_strong_closure` and "
        "`no_default_only_runtime_status` are compact diagnostic-only "
        "`operator_summary.json` summaries"
    ) in closure
    assert "They do not create apply gates" in closure
    assert "do not replace `reports/operator_summary.json` authority" in closure


def test_operator_docs_name_load_safe_apply_as_hsconfig_policy():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "`load_safe_apply` is an HSConfig operator policy" in text
    assert "not a HearthRanger public-doc term" in text
    assert "per-card-every-card coverage is HSConfig rich output" in text


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


def test_current_truth_names_source_contract_spine_brainstorm_package():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "2026-07-12-hsconfig-source-contract-spine-brainstorm" in text
    assert "Contract-spine freeze and no-second-gate evidence" in text
    assert "Keep `operator_summary.json` as the normal apply authority" in text
    assert "`source_contract_audit.json` and `contract_spine_rows` remain diagnostic" in text


def test_source_contract_spine_brainstorm_readme_marks_evidence_only():
    root = Path("docs/research/2026-07-12-hsconfig-source-contract-spine-brainstorm")
    readme = (root / "README.md").read_text(encoding="utf-8")

    assert "Research evidence only" in readme
    assert "not operator instructions" in readme
    assert "not runtime input" in readme
    assert "does not grant runtime apply permission" in readme
    assert "`operator_summary.json` remains the normal apply authority." in readme
    assert "`source_contract_audit.json` remains diagnostic." in readme
    assert "`contract_spine_rows` remain diagnostic." in readme
    assert (root / "fields.yaml").exists()
    assert (root / "outline.yaml").exists()
    assert len(list((root / "results").glob("*.json"))) == 3


def test_current_truth_names_2026_07_14_contract_guardrail_audit():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")
    audit_readme = Path(
        "docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/README.md"
    ).read_text(encoding="utf-8")

    assert "2026-07-14-hsconfig-source-contract-logic-guardrail-audit" in text
    assert "Contract-spine Guardrail v2 evidence" in text
    assert "Research evidence only" in audit_readme
    assert "not operator instructions" in audit_readme
    assert "not runtime input" in audit_readme
    assert "`operator_summary.json` remains the normal apply authority." in audit_readme
    assert "`source_contract_audit.json` remains diagnostic." in audit_readme
    assert "`source_to_runtime_explainability.json` remains diagnostic." in audit_readme


def test_research_readme_points_to_current_truth_index():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "docs/research/current-truth.md" in text
    assert "Current truth index" in text
    assert ("current truth file" in text) or (
        "only place that names the active evidence packages" in text
    )


def test_current_truth_names_post_contract_closure_audit():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "2026-07-10-hsconfig-post-contract-closure-skill-audit" in text
    assert "Post-contract no-block cleanup evidence" in text
    assert "per-card-every-card coverage is HSConfig rich output" in text


def test_current_truth_names_live_skill_audit_without_operator_drift():
    current_truth = Path("docs/research/current-truth.md").read_text(encoding="utf-8")
    audit_readme = Path(
        "docs/research/2026-07-11-hsconfig-live-skill-audit/README.md"
    ).read_text(encoding="utf-8")

    assert "2026-07-11-hsconfig-live-skill-audit" in current_truth
    assert "Live skill audit evidence" in current_truth
    assert "Research evidence only" in audit_readme
    assert "not operator instructions" in audit_readme
    assert "not runtime input" in audit_readme
    assert "Presume/Concede stale citation notes are superseded" in current_truth


def test_operator_docs_explain_mechanic_drift_without_new_gate():
    docs = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path("docs/operator/universal-wild-no-block-contract.md").read_text(
                encoding="utf-8"
            ),
        ]
    )
    assert "reports/mechanic_drift_report.json" in docs
    assert "mechanic_drift_summary" in docs
    assert "Unknown mechanics are warning-only and do not block load-safe apply" in docs
    assert "Mechanic drift is not a runtime apply gate" in docs


def test_operator_docs_explain_executable_mechanic_lowering_gap_contract():
    docs = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path("docs/operator/universal-wild-no-block-contract.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "mechanic lowering registry" in docs.lower()
    assert "cards_needing_mechanic_lowering" in docs
    assert "needs_mechanic_lowering" in docs
    assert "documented default CardID lowering target" in docs
    assert "Dredge, Tradeable, and unknown future mechanics" in docs
    assert "do not increment `cards_needing_mechanic_lowering`" in docs


def test_active_docs_do_not_reintroduce_stale_matrix_counts_or_closure_targets():
    active_files = [
        "README.md",
        "docs/operator/README.md",
        "docs/operator/universal-wild-no-block-contract.md",
        "docs/operator/source-backed-strong-closure.md",
        ".agents/skills/hsconfig/SKILL.md",
        ".agents/skills/hsconfig/references/workflow.md",
        "docs/research/current-truth.md",
    ]
    forbidden = [
        "four core_source_backed_fixture rows",
        "4 core_source_backed_fixture rows",
        "seven source_informed_valid_fixture rows",
        "7 source_informed_valid_fixture rows",
        "Next actionable closure target after durable Boarlock preservation",
        "Close the current Kingslayer and Boarlock",
    ]
    required = [
        "After durable Boarlock and Kingslayer preservation, the current actionable source-informed closure targets are",
        "Research artifacts are evidence, not operator instructions.",
    ]

    active_text = "\n".join(
        Path(active_file).read_text(encoding="utf-8") for active_file in active_files
    )
    current_truth_text = Path("docs/research/current-truth.md").read_text(
        encoding="utf-8"
    )

    for stale_claim in forbidden:
        assert stale_claim not in active_text
    for current_claim in required:
        assert current_claim in current_truth_text


def test_operator_docs_explain_no_block_failure_mode_summary():
    docs = "\n".join(
        [
            Path("docs/operator/README.md").read_text(encoding="utf-8"),
            Path("docs/operator/universal-wild-no-block-contract.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "no_block_failure_mode_summary" in docs
    assert "technical_hard_block" in docs
    assert "source_depth_warning" in docs
    assert "warning_only_mechanic" in docs
    assert "future_mechanic_drift" in docs
    assert "guide_strength_gap" in docs
    assert "combo_uncertainty" in docs
    assert "runtime_evidence_only_tuning" in docs
    assert "It does not create a second apply path." in docs


def test_operator_docs_explain_source_contract_audit_as_diagnostic_only():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "reports/source_contract_audit.json" in text
    assert "why each source claim did or did not lower to runtime config" in text
    assert "does not replace `reports/operator_summary.json`" in text


def test_current_truth_names_no_block_failure_mode_audit_v5():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "2026-07-10-hsconfig-universal-no-block-skill-audit-v5" in text
    assert "No-block failure-mode summary evidence" in text


def test_acceptance_matrix_is_documented_as_diagnostic_only():
    operator = Path("docs/operator/README.md").read_text(encoding="utf-8")
    contract = Path("docs/operator/universal-wild-no-block-contract.md").read_text(
        encoding="utf-8"
    )

    assert "hsconfig acceptance-matrix" in operator
    assert "diagnostic only" in operator
    assert "does not write runtime files" in operator
    assert "does not parse replays" in operator
    assert "does not replace `reports/operator_summary.json`" in operator
    assert "does not change the apply gate" in contract
    assert "guarded `hsconfig apply` path" in contract


def test_superpowers_artifacts_are_historical_not_operator_guidance():
    root = Path("docs/superpowers/README.md").read_text(encoding="utf-8")
    plans = Path("docs/superpowers/plans/README.md").read_text(encoding="utf-8")
    combined = f"{root}\n{plans}"

    assert "Historical planning artifacts" in root
    assert "not operator instructions" in combined
    assert "docs/operator/README.md" in combined
    assert "docs/research/current-truth.md" in combined
    assert "Do not use old Superpowers plans as the normal command path." in plans
    assert "normal command path is `hsconfig configure`" in plans


def test_historical_design_spec_carries_strong_superseded_warning():
    text = Path("docs/superpowers/specs/2026-07-05-hsconfig-design.md").read_text(
        encoding="utf-8"
    )

    assert "Superseded normal-path warning" in text
    assert (
        "Later references to optional `Presume.json` or `Concede.json` are historical"
        in text
    )
    assert (
        "normal HSConfig output must not emit `Presume.json` or `Concede.json`"
        in text
    )
    assert "docs/operator/README.md" in text
    assert ".agents/skills/hsconfig/SKILL.md" in text


def test_current_truth_prevents_old_evidence_from_overriding_operator_path():
    text = Path("docs/research/current-truth.md").read_text(encoding="utf-8")

    assert "Active docs win over historical evidence" in text
    assert "Do not start a new architecture wave from superseded research alone." in text
    assert (
        "Use real deck output or live mechanic drift as the trigger for new implementation work."
        in text
    )
    assert "replay tuning, winrate gates, or candidate promotion" in text
    assert "unless the active docs explicitly reintroduce it" in text


def test_research_readme_names_current_truth_as_only_active_evidence_index():
    text = Path("docs/research/README.md").read_text(encoding="utf-8")

    assert "only active evidence index" in text
    assert "older research folders are historical evidence" in text


def test_operator_docs_explain_effect_semantics_are_not_mulligan_keeps():
    text = Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")

    assert "Effect semantics are not opening-hand mulligan keeps" in text
    assert "Start-of-game" in text
    assert "operator_summary.json remains the normal apply authority" in text


def test_guide_research_policy_documents_evergreen_wild_source_closure():
    text = Path("docs/operator/guide-research-policy.md").read_text(encoding="utf-8")

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
        assert term in text


def test_source_builder_workflow_marks_source_informed_apply_as_legacy_noop():
    text = Path("docs/operator/source-builder-workflow.md").read_text(encoding="utf-8")

    assert "older source-informed summaries are legacy compatibility exceptions" not in text
    assert "`--allow-source-informed` is a backward-compatible legacy no-op." in text
    assert "It does not create a second apply path." in text
    assert "Runtime apply decisions come from `reports/operator_summary.json`." in text


def test_operator_readme_starts_with_short_configure_path():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")
    first_120_lines = "\n".join(text.splitlines()[:120])

    assert "hsconfig configure" in first_120_lines
    assert "reports/operator_summary.json" in first_120_lines
    assert "contract-spine-sentinel" not in first_120_lines
