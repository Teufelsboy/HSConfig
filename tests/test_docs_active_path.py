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
    assert "The lower-level normal path remains available for inspected work:" in text
    assert (
        "source-manifest -> draft-source-documents -> research-deck -> "
        "prepare -> validate -> apply"
    ) in text
    assert "HSConfig is pre-run only" in text


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
        "After durable Boarlock and Kingslayer preservation, there is no current actionable source-informed closure target.",
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
    assert "It does not create a second apply gate." in docs


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
