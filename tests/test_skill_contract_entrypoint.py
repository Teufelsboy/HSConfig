from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "hsconfig"
CHECKLIST = SKILL_ROOT / "references" / "contract-compiler-checklist.md"
ENTRYPOINT_LINK = "Contract compiler checklist: `references/contract-compiler-checklist.md`."

REQUIRED_CHECKLIST_LINES = [
    "1. Currentness gate: run `git fetch --all --prune --tags`, `python scripts/check_hsconfig_currentness.py --cwd . --json`, and `git status --short --branch` before runtime-facing work.",
    "2. Source gate: candidate registries and `source_closure_intake_receipt.json` are acquisition input only; they cannot promote, block, write runtime config, or replace `reports/operator_summary.json`.",
    "3. Claim gate: source text must normalize to an explicit `claim_kind`; effect relevance, guide importance, and archetype value do not bypass claim-kind or surface gates.",
    "4. Runtime gate: normal output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact ordered combo evidence.",
    "5. Quality gate: no silent default-only runtime success; every expected surface is emitted, explicitly suppressed, or reported as a visible source/action gap.",
    "6. Strong gate: `SOURCE_BACKED_STRONG` requires honest source closure and `default_only_runtime_surfaces=[]`; it is not needed for load-safe apply.",
    "7. No-block gate: source warnings, warning-only mechanics, unresolved options, and thin guide coverage do not block a technically valid load-safe package.",
    "8. Operator gate: open `reports/operator_summary.json` first; it remains the only normal apply authority.",
    "9. Darkbishop gate: preserve `SW_448` hero-power-transform semantics, but do not emit a Mulligan keep without explicit opening-hand source text.",
    "10. Boundary gate: do not add `Presume.json`, `Concede.json`, aggregate `CardBehavior.json`, replay parsing, winrate analysis, HSTuner tuning, or gameplay sequencing logic.",
]

FORBIDDEN_CHECKLIST_PHRASES = [
    "source report apply authority",
    "candidate URL proves strong",
    "default-only strong",
    "normal HSConfig output includes `Presume.json`",
    "normal HSConfig output includes `Concede.json`",
    "parse runtime logs to tune values",
    "HSTuner fallback",
]


def test_skill_and_workflow_link_contract_compiler_checklist():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(
        encoding="utf-8"
    )

    assert CHECKLIST.exists()
    assert ENTRYPOINT_LINK in skill
    assert ENTRYPOINT_LINK in workflow
    assert skill.count(ENTRYPOINT_LINK) == 1
    assert workflow.count(ENTRYPOINT_LINK) == 1


def test_contract_compiler_checklist_owns_canonical_runtime_boundaries():
    text = CHECKLIST.read_text(encoding="utf-8")

    assert text.count("# Contract Compiler Checklist") == 1
    for line in REQUIRED_CHECKLIST_LINES:
        assert line in text
    assert "`operator_summary.json` remains the only normal apply authority." in text
    assert "`source_contract_audit.json` is diagnostic." in text
    assert "`source_to_runtime_explainability.json` is diagnostic." in text
    assert "`source_evidence_closure.json` is diagnostic." in text


def test_contract_compiler_checklist_does_not_expand_runtime_scope():
    text = CHECKLIST.read_text(encoding="utf-8")
    lowered = text.lower()

    for phrase in FORBIDDEN_CHECKLIST_PHRASES:
        assert phrase.lower() not in lowered
    assert "does not parse replays" in lowered
    assert "does not inspect winrate" in lowered
    assert "does not analyze runtime logs" in lowered
    assert "does not tune after games" in lowered
