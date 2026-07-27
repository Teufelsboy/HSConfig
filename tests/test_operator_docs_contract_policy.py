from argparse import Namespace
import json
from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.commands.apply import apply_payload
from hsconfig.io import write_json
from hsconfig.runtime_apply import apply_package


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "hsconfig"
SKILL_ENTRYPOINT = SKILL_ROOT / "SKILL.md"
SKILL_REFERENCE_RELATIVE_PATHS = [
    Path("references/workflow.md"),
    Path("references/visionai-surfaces.md"),
    Path("references/contract-compiler-checklist.md"),
    Path("references/guide-research-policy.md"),
    Path("references/globalvalues-policy.md"),
    Path("references/card-behavior-policy.md"),
]
INSTALLED_HSCONFIG_ROOT = Path.home() / ".codex" / "skills" / "hsconfig"
INSTALLED_HSCONFIG_SKILL = INSTALLED_HSCONFIG_ROOT / "SKILL.md"
TASK7_OPERATOR_DOCS = [
    "docs/operator/source-backed-strong-closure.md",
    "docs/operator/guide-research-policy.md",
]
TASK9_OPERATOR_DOCS = [
    "docs/operator/README.md",
    "docs/operator/guide-research-policy.md",
    "docs/operator/universal-wild-no-block-contract.md",
]
SEMANTIC_SAFETY_WAVE_SENTINELS = [
    "`SOURCE_BACKED_STRONG` proves source closure only. It is necessary but not sufficient for semantic handoff.",
    "Read `semantic_handoff_status` and `semantic_handoff_reasons` before describing a package as semantically closed.",
    "Never lower generic gameplay “keep” prose into `Mulligan.json`; explicit opening-hand or Mulligan context is required.",
    "Reject the whole runtime row when any structured condition atom is unsupported.",
    "Targeting claims count as closed only when target scope and a compatible target surface are both encoded.",
    "Do not emit generic `InHandPlayPriority` or `BeforePlayCardBonus` rows solely to make every-card coverage appear complete.",
    "`reports/operator_summary.json` remains the only normal apply authority.",
    "`semantic_handoff_status` is diagnostic and never creates a second apply gate.",
]

SOURCE_BACKED_STRONG_TASK7_SENTINELS = [
    "Source-candidate registries are acquisition seeds only, not promotion authority.",
    "Candidate URLs must never promote `SOURCE_BACKED_STRONG` without fetched full-text, deck-matched, claim-kind-normalized, surface-gated evidence.",
    "No default-only runtime success: every emitted/expected runtime surface must be visible in `operator_summary.json.surface_status_ledger` or source-to-runtime diagnostics.",
    "`source_autopilot_report.json` is source-strength preflight only; `operator_summary.json` remains the normal apply authority.",
    "`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation/apply gate.",
    "Darkbishop boundary: preserve start-of-game and hero-power-transform semantics, but do not infer opening-hand keep without explicit keep text.",
    "Profile-aware closure and first-missing maps by card/surface are diagnostics.",
    "No conservative blocking: any valid deck still builds load-safe even with partial evidence; visible source actions replace blocking.",
]
CANONICAL_SOURCE_STATUS_SENTINELS = [
    "src/hsconfig/source_status_resolver.py",
    "source_backed_status",
    "source_strong_ready",
    "first_missing_source_action",
    "source_missing_source_actions",
    "source_status_reasons",
    "source_status_diagnostic_only",
    "source_status_apply_blocking",
]
SOURCE_STATUS_DIAGNOSTIC_SENTINELS = [
    "`source_status_apply_blocking` must remain `false`",
    "`default_only` is visible quality debt, not an apply blocker",
    "source-preflight diagnostic, not runtime-package proof",
    "candidate URLs promotion authority",
]
SOURCE_CONTRACT_ACCEPTANCE_DOCS = [
    "docs/operator/source-backed-strong-closure.md",
    "docs/operator/universal-wild-no-block-contract.md",
    ".agents/skills/hsconfig/SKILL.md",
]
SOURCE_CLOSURE_INTAKE_DOCS = [
    "docs/operator/source-builder-workflow.md",
    "docs/operator/universal-wild-no-block-contract.md",
    ".agents/skills/hsconfig/SKILL.md",
]
REQUIRED_CONTRACT_PHRASES = [
    "operator_summary.json remains the only normal apply authority",
    "SOURCE_BACKED_STRONG is an evidence-quality label",
    "source_status_apply_blocking must remain false",
    "default-only runtime surfaces prevent SOURCE_BACKED_STRONG",
    "Darkbishop Benedictus",
]
STALE_CONTRACT_TERMS = [
    "source report apply authority",
    "candidate url proves strong",
    "default-only strong",
]
SOURCE_INPUT_CONTRACT = (
    ROOT
    / "docs"
    / "operator"
    / "source-inputs"
    / "2026-07-17-user-wild-source-cross-check.json"
)
SOURCE_RESEARCH_RESULTS = (
    ROOT
    / "docs"
    / "research"
    / "2026-07-17-hsconfig-source-contract-acceptance-loop"
    / "results"
)
SHADOWPRIEST_ACTIVE_PLAN = (
    ROOT / "docs/superpowers/plans/2026-07-27-shadowpriest-live-config-apply.md"
)
SHADOWPRIEST_ACTIVE_SPEC = (
    ROOT / "docs/superpowers/specs/2026-07-27-shadowpriest-live-config-apply-design.md"
)
SOURCE_PROVENANCE_DIAGNOSTIC_SENTINELS = [
    "`reports/source_evidence_closure.json` is the compact diagnostic package-quality closure summary.",
    "decklists, HSReplay/HSGuru aggregate stats, static card databases, `policy_fallback`, `default_runtime`, and runtime examples are support/diagnostic only",
    "does not bypass URL validation",
]
STALE_SOURCE_STATUS_TERMS = [
    "source_closure_contract_proof",
    "strong_receipt",
    "source_class_max_ceiling",
    "effective_source_status",
    "promotion_blocker_reason",
]


def _compact(text: str) -> str:
    return " ".join(text.lower().split())


def _repo_skill_docs_text() -> str:
    paths = [SKILL_ENTRYPOINT] + [
        SKILL_ROOT / relative_path for relative_path in SKILL_REFERENCE_RELATIVE_PATHS
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _installed_skill_docs_text() -> str:
    if not INSTALLED_HSCONFIG_SKILL.exists():
        return ""

    paths = [INSTALLED_HSCONFIG_SKILL] + [
        INSTALLED_HSCONFIG_ROOT / relative_path
        for relative_path in SKILL_REFERENCE_RELATIVE_PATHS
    ]
    return "\n".join(
        path.read_text(encoding="utf-8") for path in paths if path.exists()
    )


def _source_contract_doc_text(relative_path: str) -> str:
    if relative_path == ".agents/skills/hsconfig/SKILL.md":
        return _repo_skill_docs_text()
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _line_starting(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line
    raise AssertionError(f"Missing line starting with {prefix!r}")


def _line_containing(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line:
            return line
    raise AssertionError(f"Missing line containing {needle!r}")


def _section(text: str, heading: str) -> str:
    start = text.index(heading)
    next_heading = text.find("\n## ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def _markdown_table(text: str, heading: str) -> dict[str, dict[str, str]]:
    section = _section(text, heading)
    table_lines = [line for line in section.splitlines() if line.startswith("|")]
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: dict[str, dict[str, str]] = {}
    for line in table_lines[2:]:
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        row = dict(zip(headers, cells, strict=True))
        rows[cells[0]] = row
    return rows


def _assert_task7_sentinels(text: str) -> None:
    for sentinel in SOURCE_BACKED_STRONG_TASK7_SENTINELS:
        assert sentinel in text


def test_source_backed_strong_operator_docs_state_task7_contracts():
    for relative_path in TASK7_OPERATOR_DOCS:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        try:
            _assert_task7_sentinels(text)
        except AssertionError as exc:
            raise AssertionError(
                f"{relative_path} is missing one or more Task 7 sentinels"
            ) from exc


def test_operator_docs_state_semantic_safety_wave_contracts():
    for relative_path in TASK9_OPERATOR_DOCS:
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for sentinel in SEMANTIC_SAFETY_WAVE_SENTINELS:
            assert sentinel in text, f"{relative_path}: {sentinel}"


def test_runtime_match_is_post_apply_install_integrity_only() -> None:
    text = (ROOT / "docs" / "operator" / "README.md").read_text(encoding="utf-8")

    assert "### Runtime package match" in text
    assert "semantically matches the validated package" in text
    assert "runtime-match --package <package> --runtime-root C:\\Users\\darbo\\Desktop\\HS --json" in text
    assert "`runtime-match` does not grant apply permission and never writes runtime files." in text
    assert "Apply permission still comes only from `reports/operator_summary.json`." in text


def test_repo_hsconfig_skill_states_task7_contracts():
    text = _repo_skill_docs_text()

    _assert_task7_sentinels(text)


def test_installed_hsconfig_skill_states_task7_contracts_when_present():
    if not INSTALLED_HSCONFIG_SKILL.exists():
        return

    text = _installed_skill_docs_text()

    _assert_task7_sentinels(text)


def test_active_docs_and_skill_name_canonical_source_status_resolver():
    combined = "\n".join(
        [
            (ROOT / "docs/operator/source-backed-strong-closure.md").read_text(
                encoding="utf-8"
            ),
            (ROOT / "docs/operator/universal-wild-no-block-contract.md").read_text(
                encoding="utf-8"
            ),
            _repo_skill_docs_text(),
        ]
    )

    for sentinel in CANONICAL_SOURCE_STATUS_SENTINELS:
        assert sentinel in combined


def test_active_docs_and_skill_state_source_status_is_diagnostic_not_apply_gate():
    combined = "\n".join(
        [
            (ROOT / "docs/operator/source-backed-strong-closure.md").read_text(
                encoding="utf-8"
            ),
            (ROOT / "docs/operator/universal-wild-no-block-contract.md").read_text(
                encoding="utf-8"
            ),
            _repo_skill_docs_text(),
        ]
    )

    for sentinel in SOURCE_STATUS_DIAGNOSTIC_SENTINELS:
        assert sentinel in combined
    for sentinel in SOURCE_PROVENANCE_DIAGNOSTIC_SENTINELS:
        assert sentinel in combined


def test_active_docs_and_skill_state_strong_closure_dossier_boundary():
    combined = "\n".join(
        [
            (ROOT / "docs/operator/source-backed-strong-closure.md").read_text(
                encoding="utf-8"
            ),
            _repo_skill_docs_text(),
        ]
    )

    for sentinel in (
        "hsconfig strong-closure-dossier",
        "strong-closure-dossier is diagnostic-only",
        "operator_summary.json remains the only normal apply authority",
    ):
        assert sentinel in combined


def test_active_docs_and_skill_state_source_contract_acceptance_loop_exact_phrases():
    for relative_path in SOURCE_CONTRACT_ACCEPTANCE_DOCS:
        text = _source_contract_doc_text(relative_path)
        lowered = text.lower()

        for phrase in REQUIRED_CONTRACT_PHRASES:
            assert phrase in text
        for stale_term in STALE_CONTRACT_TERMS:
            assert stale_term not in lowered


def test_active_docs_and_skill_state_source_closure_intake_receipt_boundary():
    combined = "\n".join(
        (ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in SOURCE_CLOSURE_INTAKE_DOCS
    )
    lowered = combined.lower()

    for sentinel in (
        "source_closure_intake_receipt.json",
        "source_closure_intake",
        "authority=diagnostic_only",
        "source_status_apply_blocking=false",
        "cannot promote",
        "cannot block",
        "cannot write runtime config",
        "cannot replace `reports/operator_summary.json`",
    ):
        assert sentinel in combined
    assert "source_closure_intake_receipt.json remains the normal apply authority" not in lowered


def test_user_wild_source_input_keeps_unfetched_candidates_non_authoritative():
    payload = json.loads(SOURCE_INPUT_CONTRACT.read_text(encoding="utf-8"))

    assert payload["usage"] == "source_candidates_only_not_runtime_authority"
    assert len(payload["decks"]) == 12
    for deck in payload["decks"]:
        assert deck["deck_name"]
        assert deck["deck_code"]
        assert deck["first_missing_source_action"]
        for record in deck["source_candidates"]:
            assert record["source_strength"] == "unfetched_acquisition_seed"
            assert record["promotion_role"] == (
                "candidate_only_until_fetched_and_claim_normalized"
            )
            assert record["classification_note"] == (
                "must_be_fetched_and_claim_normalized_before_source_strength_or_runtime_use"
            )
        for record in deck["non_promoting_support"]:
            assert record["promotion_role"] == "context_only"


def test_research_results_keep_source_strength_and_authority_separate():
    result_files = sorted(SOURCE_RESEARCH_RESULTS.glob("*.json"))
    seed_or_non_promoting_strengths = {
        "unfetched_acquisition_seed",
        "decklist_or_stats_only",
        "missing",
    }
    allowed_strengths = seed_or_non_promoting_strengths | {"exact_full_text_guide"}
    current_or_evergreen = {"current", "current_or_evergreen", "evergreen"}

    assert len(result_files) == 12
    for result_file in result_files:
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        source_strength = payload["source_strength"]
        first_missing = payload["first_missing_source_action"]

        assert source_strength in allowed_strengths

        if source_strength in seed_or_non_promoting_strengths:
            assert first_missing != "none"
            assert (
                "not runtime authority" in payload["notes"]
                or "SOURCE_BACKED_PARTIAL" in payload["notes"]
            )

        if (
            source_strength == "exact_full_text_guide"
            and payload.get("freshness_status") not in current_or_evergreen
        ):
            assert first_missing != "none"
            assert any(
                guide_source.get("promotes_strong") is False
                for guide_source in payload.get("guide_sources", [])
            )


def test_active_source_status_contract_does_not_reintroduce_stale_terms():
    active_text = "\n".join(
        [
            (ROOT / "docs/operator/source-backed-strong-closure.md").read_text(
                encoding="utf-8"
            ),
            (ROOT / "docs/operator/universal-wild-no-block-contract.md").read_text(
                encoding="utf-8"
            ),
            _repo_skill_docs_text(),
        ]
    )

    for stale_term in STALE_SOURCE_STATUS_TERMS:
        assert stale_term not in active_text


def test_installed_hsconfig_skill_does_not_reintroduce_stale_source_status_terms_when_present():
    if not INSTALLED_HSCONFIG_SKILL.exists():
        return

    text = _installed_skill_docs_text()

    for sentinel in CANONICAL_SOURCE_STATUS_SENTINELS:
        assert sentinel in text
    for sentinel in SOURCE_STATUS_DIAGNOSTIC_SENTINELS[:2]:
        assert sentinel in text
    for stale_term in STALE_SOURCE_STATUS_TERMS:
        assert stale_term not in text


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
- normal path does not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`
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
    text = _repo_skill_docs_text()

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
    skill = _repo_skill_docs_text()
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
    assert (
        "normal HSConfig output must not emit `Presume.json`, `Concede.json`, or"
    ) in combined
    assert "aggregate `CardBehavior.json`" in combined


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


def test_active_shadowpriest_documents_keep_canonical_receipts_diagnostic_only():
    plan = SHADOWPRIEST_ACTIVE_PLAN.read_text(encoding="utf-8")
    spec = SHADOWPRIEST_ACTIVE_SPEC.read_text(encoding="utf-8")
    active_documents = f"{plan}\n{spec}"

    assert "`operator_summary.json` is the sole normal apply authority" in plan
    assert 'assert claims["canonical_source_receipts"]' not in plan
    assert "canonical_source_receipts must be nonempty" not in active_documents.lower()

    canonical_receipt_diagnostic_section = _section(
        plan, "## Canonical receipt diagnostic correction (2026-07-28)"
    )
    assert "stop before apply" not in canonical_receipt_diagnostic_section.lower()
    assert (
        "Canonical receipt count and exact-source closure are diagnostics. Empty exact\n"
        "source evidence must remain visible, but it does not create a second apply\n"
        "authority. The operator decision is read only from reports/operator_summary.json;\n"
        "the apply command independently recomputes package integrity and parity."
        in active_documents
    )


def test_operator_docs_and_skill_name_mulligan_policy_status_without_strong_promotion():
    active_text = "\n".join(
        [
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "docs" / "operator" / "README.md").read_text(encoding="utf-8"),
            (
                ROOT / "docs" / "operator" / "universal-wild-no-block-contract.md"
            ).read_text(encoding="utf-8"),
            _repo_skill_docs_text(),
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
    assert "not an apply authority" in text
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


def test_operator_docs_name_source_autopilot_without_new_apply_gate():
    readme = (ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )
    policy = (ROOT / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    skill = _repo_skill_docs_text()
    combined = f"{readme}\n{policy}\n{skill}"

    assert "--auto-source" in combined
    assert "source-autopilot" in combined
    assert "02_source_autopilot" in combined
    assert "static records without explicit supported effect semantics do not promote `SOURCE_BACKED_STRONG`" in combined
    assert "static records without explicit runtime-surface claims" not in combined
    assert "Core source-backed fixtures should cover ShadowPriest, BigShaman, Discolock" not in combined
    assert "current actionable source-informed closure targets are CtAPaladin, Discolock, TreantDruid, and PirateDH" in combined
    assert "`source-autopilot` is source-strength preflight, not runtime apply authority." in combined
    assert "operator_summary.json remains the only normal apply authority" in combined


def test_source_closure_docs_keep_research_sentinel_non_promoting() -> None:
    text = Path("docs/operator/source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )

    assert "research-result sentinel" in text
    assert "cannot promote or downgrade" in text
    assert "source_status_apply_blocking=false" in text


def test_operator_docs_keep_single_apply_authority_and_no_default_only_visibility():
    guide = (ROOT / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    skill = _repo_skill_docs_text()
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
            _repo_skill_docs_text(),
        ]
    )

    assert "per-card closure" in active_text
    assert "default_only_runtime_surface_details" in active_text
    assert "operator_summary.json remains the only normal apply authority" in active_text
    assert "source_to_runtime_explainability.json" in active_text
    assert "source_evidence_closure.json" in active_text


def test_active_docs_describe_fresh_closure_proof_without_new_apply_gate():
    operator = (ROOT / "docs/operator/README.md").read_text(encoding="utf-8")
    policy = (ROOT / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    skill = _repo_skill_docs_text()
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
    skill_text = _repo_skill_docs_text()
    skill_policy_text = (
        root / ".agents/skills/hsconfig/references/guide-research-policy.md"
    ).read_text(encoding="utf-8")
    combined = "\n".join([docs_text, policy_text, skill_text, skill_policy_text])

    assert (
        "source_to_runtime_explainability.json is the primary card-readable repair map"
        in combined
    )
    assert "source_evidence_closure.json is the compact diagnostic package-quality summary" in combined
    assert "source_claim_gap_report.json is secondary diagnostic evidence" in combined
    assert "Use `source_claim_gap_report.json` to inspect the first missing source" not in combined
    assert "operator_summary.json remains the only normal apply authority" in combined


def test_docs_and_skill_route_configure_source_closure_receipt_without_second_gate():
    active_text = "\n".join(
        [
            (ROOT / "docs/operator/README.md").read_text(encoding="utf-8"),
            _repo_skill_docs_text(),
            (
                ROOT / ".agents/skills/hsconfig/references/workflow.md"
            ).read_text(encoding="utf-8"),
        ]
    )

    assert "configure_summary.json.source_closure_receipt" in active_text
    assert "compact diagnostic-only source-closure receipt" in active_text
    assert "does not replace `reports/operator_summary.json`" in active_text
    assert "cannot promote, block, apply, or write runtime files" in active_text
    assert "source_status_apply_blocking=false" in active_text
    assert "default-only runtime surfaces remain visible quality debt" in active_text
    assert "source_closure_receipt remains the normal apply authority" not in active_text.lower()


def test_skill_workflow_routes_configure_source_closure_receipt_with_out_prefix():
    text = (
        ROOT
        / ".agents"
        / "skills"
        / "hsconfig"
        / "references"
        / "workflow.md"
    ).read_text(encoding="utf-8")

    assert "`<out>/configure_summary.json.source_closure_receipt`" in text


def test_skill_normal_workflow_routes_generated_receipts_in_order():
    workflow = (
        ROOT / ".agents" / "skills" / "hsconfig" / "references" / "workflow.md"
    ).read_text(encoding="utf-8")
    normal_workflow = _line_containing(workflow, "Normal workflow:")
    routes = [
        "`<out>/configure_summary.json.acceptance_summary`",
        "`<out>/configure_summary.json.handoff_contract`",
        "`<out>/configure_summary.json.source_closure_receipt`",
    ]

    for route in routes:
        assert route in normal_workflow
    assert normal_workflow.index(routes[0]) < normal_workflow.index(routes[1])
    assert normal_workflow.index(routes[1]) < normal_workflow.index(routes[2])
    assert "when source depth is the question" in normal_workflow
    assert "diagnostic-only" in normal_workflow
    assert "use `reports/operator_summary.json` as the apply authority" in normal_workflow
    assert "source_closure_receipt remains the normal apply authority" not in _compact(
        normal_workflow
    )


def test_real_deck_loop_routes_source_receipt_without_new_gate():
    text = (ROOT / "docs/operator/README.md").read_text(encoding="utf-8")
    loop = _section(text, "## Real-Deck Usage Loop")
    acceptance = "`<out>/configure_summary.json.acceptance_summary`"
    handoff = "`<out>/configure_summary.json.handoff_contract`"
    source_receipt = "`<out>/configure_summary.json.source_closure_receipt`"

    assert acceptance in loop
    assert handoff in loop
    assert source_receipt in loop
    assert loop.index(acceptance) < loop.index(handoff)
    assert loop.index(handoff) < loop.index(source_receipt)
    assert "source-contract and no-default-only diagnostics" in loop
    assert "without treating them as extra gates" in loop
    assert "source_closure_receipt remains the normal apply authority" not in _compact(
        loop
    )
    assert "source_closure_receipt gate" not in _compact(loop)
    assert f"{source_receipt} as the apply authority" not in loop


def test_source_closure_receipt_explanatory_paragraph_uses_out_prefix():
    text = (ROOT / "docs/operator/README.md").read_text(encoding="utf-8")
    paragraph = _line_containing(
        text,
        "configure_summary.json.source_closure_receipt` is the compact diagnostic-only source-closure receipt",
    )

    assert paragraph.startswith(
        "`<out>/configure_summary.json.source_closure_receipt`"
    )


def test_exact_guide_mulligan_gate_is_machine_readable_and_fail_closed() -> None:
    policy = (ROOT / "docs/operator/guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    gate = _markdown_table(policy, "### Exact Public-Guide Mulligan Gate")

    assert set(gate) == {
        "public_guide_identity",
        "deck_match_scope",
        "target_deck_fingerprint",
        "exact_deck_evidence",
        "source_receipt",
        "promotion_eligible",
        "source_visibility",
        "source_lane",
    }
    assert {
        check: row["Required value"] for check, row in gate.items()
    } == {
        "public_guide_identity": (
            "all populated document and claim identity signals are guide"
        ),
        "deck_match_scope": "exact_deck_matched",
        "target_deck_fingerprint": (
            "present and equal to matched_deck_fingerprint"
        ),
        "exact_deck_evidence": (
            "matched=true; both counts >=1; non-empty code-hash list"
        ),
        "source_receipt": (
            "matching claim_id, claim signature, target fingerprint, and "
            "live_http / live_verified provenance"
        ),
        "promotion_eligible": "true",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
    }
    assert {row["Failure outcome"] for row in gate.values()} == {
        "suppress with visible reason"
    }


def test_operator_contract_models_physical_rows_and_assurance_dimensions() -> None:
    spine = (ROOT / "docs/operator/source-contract-spine.md").read_text(
        encoding="utf-8"
    )
    rows = _markdown_table(spine, "## Physical Runtime Row Contract")
    assurance = _markdown_table(spine, "## Configuration Assurance")

    assert rows["runtime_key"]["Shape"] == "(card_id, behavior_block, condition)"
    assert rows["full_signature"]["Shape"] == (
        "(card_id, behavior_block, condition, value)"
    )
    assert rows["duplicate_provenance"]["Result"] == "merge and sort provenance"
    assert rows["conflicting_values"]["Result"] == "fail closed; suppress physical row"
    assert rows["physical_report_parity"]["Shape"] == (
        "physical CardID values versus meaningful card-behavior report rows"
    )
    assert rows["physical_report_parity"]["Result"] == "exact row parity required"

    assert set(assurance) == {
        "load_safety",
        "source_authority",
        "semantic_closure",
        "in_client_behavior",
        "optimality_claim_allowed",
        "runtime_gate_impact",
    }
    assert assurance["in_client_behavior"]["Contract value"] == (
        "not_proven_by_pre_run_contract"
    )
    assert assurance["optimality_claim_allowed"]["Contract value"] == "false"
    assert assurance["runtime_gate_impact"]["Contract value"] == "none"

    surfaces = _markdown_table(spine, "## ShadowPriest Runtime Surfaces")
    assert surfaces["reciprocal_hero_burn"]["Runtime surface"] == "report-only"
    assert "state_dependent" not in surfaces


def test_operator_contract_names_globalvalues_plan_trust_boundaries() -> None:
    spine = (ROOT / "docs/operator/source-contract-spine.md").read_text(
        encoding="utf-8"
    )
    rows = _markdown_table(spine, "## GlobalValues Plan Trust Boundary")

    assert rows == {
        "legacy_claim_inference": {
            "Boundary": "legacy_claim_inference",
            "Canonical input": (
                "effective claim kind before authority-field stripping"
            ),
            "Required outcome": (
                "untyped posture text cannot mint a source receipt"
            ),
        },
        "identity_signal_layers": {
            "Boundary": "identity_signal_layers",
            "Canonical input": "document and claim identity signals together",
            "Required outcome": (
                "any explicit non-guide signal vetoes public-guide authority"
            ),
        },
        "bundle_receipt_truth": {
            "Boundary": "bundle_receipt_truth",
            "Canonical input": (
                "non-plan source-document bundle and verified receipts"
            ),
            "Required outcome": (
                "plan bundle and plan receipts cannot replace package truth"
            ),
        },
        "plan_input_diagnostics": {
            "Boundary": "plan_input_diagnostics",
            "Canonical input": "imported plan claims, rows, and receipts",
            "Required outcome": (
                "diagnostic only with runtime_gate_impact=none"
            ),
        },
        "plan_revalidation": {
            "Boundary": "plan_revalidation",
            "Canonical input": (
                "canonical lifecycle, target fingerprint, and verified receipts"
            ),
            "Required outcome": "only canonical rows may lower",
        },
        "canonical_runtime_plans": {
            "Boundary": "canonical_runtime_plans",
            "Canonical input": (
                "freshly rebuilt Mulligan, CardID, and Combo plans"
            ),
            "Required outcome": (
                "sole runtime truth; imported same-ID rows cannot replace or restore"
            ),
        },
        "imported_runtime_plan_payloads": {
            "Boundary": "imported_runtime_plan_payloads",
            "Canonical input": (
                "actual imported Mulligan, CardID, and Combo report payloads"
            ),
            "Required outcome": (
                "diagnostic only in plan_input_diagnostics with runtime_gate_impact=none"
            ),
        },
        "legacy_mulligan_receipt": {
            "Boundary": "legacy_mulligan_receipt",
            "Canonical input": "synthetic --claims-json source documents",
            "Required outcome": (
                "cannot mint a canonical exact source receipt"
            ),
        },
        "suppression_transparency": {
            "Boundary": "suppression_transparency",
            "Canonical input": (
                "key, operation, overlay, value, and claim references"
            ),
            "Required outcome": "rejected plan attempt remains reconstructible",
        },
        "exact_evidence_counts": {
            "Boundary": "exact_evidence_counts",
            "Canonical input": (
                "both count fields parsed by one strict non-negative integer parser"
            ),
            "Required outcome": (
                "integer or decimal string accepted; bool, float, container, negative, or malformed rejected without exception"
            ),
        },
        "exact_evidence_authority": {
            "Boundary": "exact_evidence_authority",
            "Canonical input": (
                "positive candidate counts and non-empty code-hash list"
            ),
            "Required outcome": (
                "otherwise no receipt and a visible exact-source gap"
            ),
        },
    }
    assert (
        "One shared `parse_strict_nonnegative_int` parser is used by\n"
        "`source_document_drafter`, `source_autopilot`, and "
        "`source_document_builder`."
    ) in spine
    assert (
        "Count rejection preserves a\nload-safe package with "
        "`SOURCE_BACKED_PARTIAL`, exposes the exact-source gap,\nand mints no "
        "receipt."
    ) in spine


def test_operator_docs_define_strategic_acquisition_authority() -> None:
    guide = (ROOT / "docs" / "operator" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )
    rows = _markdown_table(guide, "## Strategic Acquisition Authority")

    assert {
        mode: (row["Authority"], row["Strategic receipt"])
        for mode, row in rows.items()
    } == {
        "live_http": ("live_verified", "eligible after all exact guide gates"),
        "captured_record": ("captured_unverified", "no; diagnostic-only"),
        "manual_evidence": ("manual_unverified", "no; diagnostic-only"),
        "fixture_map": ("fixture_only", "no; diagnostic-only"),
        "legacy_claims_json": ("legacy_unverified", "no; diagnostic-only"),
    }
    assert (
        "Only `live_http` plus `live_verified` provenance can mint a canonical "
        "strategic source receipt."
    ) in guide
    assert (
        "Captured, fixture, manual, and legacy inputs remain diagnostic-only "
        "for strategic authority."
    ) in guide


def test_operator_docs_define_claim_kind_strong_and_combo_boundaries() -> None:
    spine = (ROOT / "docs" / "operator" / "source-contract-spine.md").read_text(
        encoding="utf-8"
    )
    rows = _markdown_table(spine, "## Claim-Kind Strong Authority")

    assert rows["strategic_claims"]["Strong authority"] == (
        "deck_matched_public_guide plus verified strategic receipt"
    )
    assert rows["deterministic_static_claims"]["Strong authority"] == (
        "deck_matched_public_guide or source_backed_static_semantics"
    )
    assert (
        "Static semantics can support deterministic CardID and effect claims, "
        "but they can never authorize strategic Combo order."
    ) in spine


def test_operator_docs_define_linked_runtime_owner_and_verification_limits() -> None:
    operator = (ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )

    linked_owner_lines = [
        "Source card: `SW_448` (Darkbishop Benedictus)",
        "Link: `hero_power_transform`",
        "Runtime owner: `EX1_625t` (Mind Spike)",
        "Physical row: `CardID/EX1_625t.json`",
    ]
    for line in linked_owner_lines:
        assert line in operator
    assert (
        "The numeric bonus is a configuration policy value, not proof of "
        "optimal play."
    ) in operator
    assert (
        "Offline tests prove neither in-client behavior nor gameplay optimality."
    ) in operator


def test_operator_apply_docs_match_cli_and_direct_prevalidation_behavior(
    tmp_path: Path,
) -> None:
    package = tmp_path / "invalid-package"
    runtime = tmp_path / "runtime"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "invalid"}
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        globalvalues,
    )
    write_json(
        package / "reports" / "globalvalues_baseline.json",
        globalvalues,
    )
    write_json(
        package / "reports" / "globalvalues_profile.json",
        {
            "key_count": len(globalvalues),
            "keys": {key: {"status": "unchanged"} for key in globalvalues},
            "generated_overlay_keys": [],
            "summary": {"all_expected_overlay_keys_accounted_for": True},
            "expected_overlay_keys": [],
            "missing_overlay_keys": [],
        },
    )
    payload, exit_code = apply_payload(
        Namespace(
            package=str(package),
            runtime_root=str(runtime),
            fake=False,
            from_fake_receipt=None,
        )
    )
    gate = evaluate_apply_gate(package)

    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["errors"]
    assert payload["validation_report"]["status"] == "failed"
    assert "apply_gate" not in payload
    assert gate["status"] == "blocked"
    assert gate["reasons"][0]["reason"] == "missing_operator_summary"

    with pytest.raises(
        ValueError,
        match="Runtime apply requires a valid complete package before",
    ):
        apply_package(
            package_root=package,
            runtime_root=runtime,
            write_history=False,
        )

    operator = (ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )
    section = _section(operator, "## Runtime Apply Authority")

    required_entrypoint_contracts = [
        (
            "The CLI and direct Python entry points both run strict complete-package "
            "validation before the shared apply gate."
        ),
        (
            "CLI prevalidation failures return `validation_report` and `errors`; "
            "they may stop before a stable apply-gate reason code exists."
        ),
        (
            "Direct `plan_apply_package()` / `apply_package()` prevalidation raises "
            "before the shared gate."
        ),
    ]
    for contract in required_entrypoint_contracts:
        assert contract in section


def test_operator_docs_define_simplified_fail_closed_gate_phases_and_codes() -> None:
    operator = (ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )
    section = _section(operator, "## Runtime Apply Authority")

    assert (
        "These are simplified fail-closed phases, not a promise that every "
        "entry point emits the same intermediate result or reason code:"
    ) in section
    required_gate_phases = [
        "Require a readable object at `reports/operator_summary.json`.",
        "Recompute deck-input verification and require runtime apply eligibility.",
        "Verify strategic source authority.",
        "Require the derivation receipt and summary derivation metadata.",
        "Verify the receipt schema and recompute its summary-bound digest.",
        "Recompute receipt content from authoritative inputs and runtime JSON.",
        "Verify exact summary derivation consistency and generated-file parity.",
        "Authorize the runtime write only for a recomputed valid package.",
    ]
    for phase in required_gate_phases:
        assert phase in section

    for reason_code in [
        "strict_package_validation_failed",
        "deck_input_not_verified",
        "source_authority_receipt_invalid",
        "package_derivation_receipt_missing",
        "package_derivation_receipt_schema_unsupported",
        "package_derivation_receipt_digest_mismatch",
        "package_derivation_mismatch",
        "operator_summary_derivation_inconsistent",
    ]:
        assert f"`{reason_code}`" in section

    assert (
        "Unverified deck input blocks apply even when a diagnostic package can "
        "still be built."
    ) in section
    assert (
        "`reports/operator_summary.json` is the sole human-facing verdict; "
        "never infer apply readiness from individual diagnostic reports."
    ) in section
    assert (
        "These codes belong to the shared gate; CLI prevalidation can instead "
        "return `validation_report` and `errors` before that gate is reached."
    ) in section


def test_operator_combo_summaries_require_live_verified_strategic_receipt() -> None:
    operator = (ROOT / "docs" / "operator" / "README.md").read_text(
        encoding="utf-8"
    )

    assert (
        "per-card `<CARDID>.json`, and `Combo.json` when exact ordered combo "
        "evidence and a matching live-verified strategic receipt exist."
    ) in operator
    assert (
        "`Combo.json` is conditional on a complete source-backed combo with a "
        "matching live-verified strategic receipt."
    ) in operator
