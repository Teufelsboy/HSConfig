from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _compact(text: str) -> str:
    return " ".join(text.lower().split())


def test_guide_research_policy_names_source_truth_boundary():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "Source Truth Is Not Runtime Authority" in text
    assert "`claim_kind` is the runtime-routing authority" in text
    assert "`operator_summary.json` remains the only normal apply authority" in text
    assert "Darkbishop Benedictus" in text
    assert "does not become a mulligan keep" in text
    assert "`globalvalue_numeric_tuning`" in text
    assert "requires runtime evidence" in text


def test_guide_research_policy_keeps_no_block_language():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "Warnings are follow-up work, not a runtime apply blocker." in text
    assert "Do not use `source_contract_audit.json` as an apply gate." in text


def test_guide_research_policy_states_the_concise_source_to_runtime_boundary():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    required_section = """## Source-To-Runtime Boundary

HSConfig separates technical load safety from source richness. A package may be
load-safe and apply-ready even when some guide claims remain diagnostic.
`reports/operator_summary.json` is the only apply authority.

`SOURCE_BACKED_STRONG` is a source-confidence label, not an apply gate.
`policy_backed_autonomous_mulligan` may prevent default-only output, but it does
not convert a claim into source-backed evidence.

Never lower these into runtime config unless the specific runtime surface is
documented and identity is resolved:

- start-of-game or deckbuilding effects as opening-hand mulligan keeps
- hero-power-transform effects as opening-hand mulligan keeps
- generated random pools as deterministic per-card behavior
- Discover or Choose One preference without exact option identity
- numeric GlobalValues tuning without runtime evidence
"""

    assert text.count("## Source-To-Runtime Boundary") == 1
    assert required_section in text


def test_universal_wild_contract_states_no_block_and_no_default_only_policy():
    text = (
        ROOT / "docs" / "operator" / "universal-wild-no-block-contract.md"
    ).read_text(encoding="utf-8")

    required_section = """## Universal No-Block Contract

For any valid deck input, HSConfig should produce a load-safe package whenever
the runtime JSON package itself is valid. Weak source richness, unknown mechanics,
report-only claims, unresolved options, or runtime-evidence-only tuning are
operator-visible diagnostics, not hard blockers.

The package must not be default-only:

- `default_only_runtime_surfaces` is empty
- `mulligan_policy_status.default_only` is `false`
- `GlobalValues.json` exists
- `Mulligan.json` exists
- every known deck CardID gets a per-card JSON file
- normal path does not emit `Presume.json` or `Concede.json`
"""

    assert text.count("## Universal No-Block Contract") == 1
    assert required_section in text


def test_operator_docs_name_canonical_lifecycle_without_second_gate():
    text = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    normalized = _compact(text)

    assert "canonical claim lifecycle" in normalized
    assert "conflict quarantine" in normalized
    assert "quarantined claims suppress unsafe runtime rows" in normalized
    assert "do not block load-safe valid packages" in normalized
    assert "operator_summary.json remains the only normal apply authority" in text
    assert "source_contract_audit.json is diagnostic" in text


def test_skill_mentions_claim_lifecycle_and_no_block_contract():
    text = (ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "canonical claim lifecycle" in text.lower()
    assert "quarantined claims suppress unsafe runtime rows" in text
    assert "do not block load-safe valid packages" in text


def test_skill_reference_mentions_claim_lifecycle_and_no_block_contract():
    text = (
        ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "guide-research-policy.md"
    ).read_text(encoding="utf-8")
    normalized = _compact(text)

    assert "canonical claim lifecycle" in normalized
    assert "conflict quarantine" in normalized
    assert "quarantined claims suppress unsafe runtime rows" in normalized
    assert "do not block load-safe valid packages" in normalized
    assert "operator_summary.json remains the only normal apply authority" in text
    assert "source_contract_audit.json" in text


def test_skill_text_names_source_contract_spine_without_runtime_surface_expansion():
    skill = (ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    reference = (
        ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "guide-research-policy.md"
    ).read_text(encoding="utf-8")
    combined = f"{skill}\n{reference}"

    assert "`claim_kind`" in combined
    assert "source contract matrix" in combined
    assert "surface gate" in combined
    assert "operator_summary.json remains the normal apply authority" in combined
    assert "Warnings are follow-up work, not runtime apply blockers." in combined
    assert "normal HSConfig output must not emit `Presume.json` or `Concede.json`" in combined


def test_operator_docs_keep_one_apply_authority_and_no_second_gate_language():
    operator_readme = (ROOT / "docs/operator/README.md").read_text(encoding="utf-8")
    guide_policy = (ROOT / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    combined = operator_readme + "\n" + guide_policy

    assert "reports/operator_summary.json remains the only normal apply authority" in combined
    assert "source_contract_audit.json is diagnostic" in combined
    assert "`source_advisory_gate` is warning/advisory only" in combined
    assert "Presume.json" in combined
    assert "Concede.json" in combined
    assert "normal-path Presume.json" not in combined
    assert "normal-path Concede.json" not in combined
    assert "normal path Presume.json" not in combined
    assert "normal path Concede.json" not in combined
    assert "block/apply-gate" not in combined


def test_operator_docs_and_skill_name_mulligan_policy_status_without_strong_promotion():
    active_text = "\n".join(
        [
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "docs" / "operator" / "README.md").read_text(encoding="utf-8"),
            (
                ROOT / "docs" / "operator" / "universal-wild-no-block-contract.md"
            ).read_text(encoding="utf-8"),
            (ROOT / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "mulligan_policy_status" in active_text
    assert "default_only_runtime_surfaces" in active_text
    assert "policy_backed_autonomous_mulligan" in active_text
    assert "must not promote" in active_text
    assert "SOURCE_BACKED_STRONG" in active_text
    assert "Darkbishop Benedictus" in active_text


def test_source_contract_spine_reference_is_active_but_not_an_apply_gate():
    text = (ROOT / "docs" / "operator" / "source-contract-spine.md").read_text(
        encoding="utf-8"
    )

    required_claim_kinds = {
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
        "discover_choice",
        "choose_one_choice",
        "globalvalue_numeric_tuning",
    }

    assert "Diagnostic reference only" in text
    assert "`reports/operator_summary.json` remains the only normal apply authority." in text
    assert "does not create a second apply gate" in text
    assert "Mulligan.json" in text
    assert "GlobalValues.json" in text
    assert "Combo.json" in text
    assert "CARDID.json" in text
    assert "Presume.json" in text
    assert "Concede.json" in text
    for claim_kind in required_claim_kinds:
        assert f"`{claim_kind}`" in text


def test_operator_readme_links_source_contract_spine_without_normal_path_drift():
    text = (ROOT / "docs" / "operator" / "README.md").read_text(encoding="utf-8")
    first_120_lines = "\n".join(text.splitlines()[:120])

    assert "docs/operator/source-contract-spine.md" in text
    assert "hsconfig configure" in first_120_lines
    assert "source-contract-spine" not in first_120_lines
    assert "source-contract-spine -> apply" not in text


def test_operator_docs_keep_single_apply_authority_and_no_default_only_visibility():
    guide = (ROOT / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    skill = (ROOT / ".agents/skills/hsconfig/SKILL.md").read_text(encoding="utf-8")
    combined = f"{guide}\n{skill}"

    assert "reports/operator_summary.json remains the only normal apply authority" in combined
    assert "diagnostic reports must not become apply gates" in combined
    assert "default-only runtime surfaces must be visible, not silent" in combined
    assert "Presume.json" in combined
    assert "Concede.json" in combined
    assert "outside the normal HSConfig path" in combined


def test_active_docs_describe_per_card_closure_without_second_gate():
    active_text = "\n".join(
        [
            (ROOT / "docs/operator/README.md").read_text(encoding="utf-8"),
            (ROOT / "docs/operator/guide-research-policy.md").read_text(
                encoding="utf-8"
            ),
            (ROOT / ".agents/skills/hsconfig/SKILL.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "per-card closure" in active_text
    assert "default_only_runtime_surface_details" in active_text
    assert "operator_summary.json remains the only normal apply authority" in active_text
    assert "source_to_runtime_explainability.json" in active_text


def test_active_docs_describe_fresh_closure_proof_without_new_apply_gate():
    operator = (ROOT / "docs/operator/README.md").read_text(encoding="utf-8")
    policy = (ROOT / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    skill = (ROOT / ".agents/skills/hsconfig/SKILL.md").read_text(
        encoding="utf-8"
    )
    active_docs = "\n".join([operator, policy, skill])

    assert "closure_schema_current" in active_docs
    assert "cards_missing_closure" in active_docs
    assert "default_only_runtime_surface_details" in active_docs
    assert (
        "operator_summary.json remains the only normal apply authority"
        in active_docs
    )
    assert "diagnostic-only" in active_docs or "diagnostic only" in active_docs


def test_operator_docs_state_no_silent_default_only_without_second_gate():
    docs = "\n".join(
        [
            (ROOT / "docs" / "operator" / "README.md").read_text(
                encoding="utf-8"
            ),
            (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    assert "no-silent-default-only" in docs.lower()
    assert "visible quality" in docs.lower()
    assert "not an apply blocker" in docs.lower()
    assert "operator_summary.json remains the only normal apply authority" in docs


def test_docs_keep_source_claim_gap_report_secondary_to_explainability():
    root = Path(__file__).resolve().parents[1]
    docs_text = (root / "docs/operator/README.md").read_text(encoding="utf-8")
    policy_text = (root / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    skill_text = (root / ".agents/skills/hsconfig/SKILL.md").read_text(
        encoding="utf-8"
    )
    skill_policy_text = (
        root / ".agents/skills/hsconfig/references/guide-research-policy.md"
    ).read_text(encoding="utf-8")
    combined = "\n".join([docs_text, policy_text, skill_text, skill_policy_text])

    assert (
        "source_to_runtime_explainability.json is the primary card-readable repair map"
        in combined
    )
    assert "source_claim_gap_report.json is secondary diagnostic evidence" in combined
    assert "Use `source_claim_gap_report.json` to inspect the first missing source" not in combined
    assert "operator_summary.json remains the only normal apply authority" in combined
