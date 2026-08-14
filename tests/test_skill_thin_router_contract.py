from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / ".agents" / "skills" / "hsconfig"
SKILL = SKILL_ROOT / "SKILL.md"
REFERENCES = [
    SKILL_ROOT / "references" / "workflow.md",
    SKILL_ROOT / "references" / "visionai-surfaces.md",
    SKILL_ROOT / "references" / "contract-compiler-checklist.md",
    SKILL_ROOT / "references" / "guide-research-policy.md",
    SKILL_ROOT / "references" / "globalvalues-policy.md",
    SKILL_ROOT / "references" / "card-behavior-policy.md",
]


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _active_reference_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in REFERENCES)


def test_hsconfig_skill_entrypoint_is_a_thin_router() -> None:
    text = _skill_text()
    lines = [line.rstrip() for line in text.splitlines()]
    non_empty_lines = [line for line in lines if line.strip()]
    long_lines = [line for line in non_empty_lines if len(line) > 220]

    assert len(non_empty_lines) <= 70
    assert long_lines == []
    assert text.count("## References:") == 1
    assert "docs/operator/README.md" in text
    for reference_path in [
        "references/workflow.md",
        "references/visionai-surfaces.md",
        "references/contract-compiler-checklist.md",
        "references/guide-research-policy.md",
        "references/globalvalues-policy.md",
        "references/card-behavior-policy.md",
    ]:
        assert reference_path in text


def test_hsconfig_skill_entrypoint_keeps_only_hard_runtime_boundaries() -> None:
    text = _skill_text()
    required_entrypoint_phrases = [
        "HSConfig is pre-run only.",
        "Preferred normal path: `hsconfig configure`.",
        "`reports/operator_summary.json` remains the only normal apply authority.",
        "`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation or apply gate.",
        "`source_status_apply_blocking` must remain `false` for source-quality work.",
        "No hidden default-only runtime success.",
        "`Combo.json` only for exact ordered combo evidence.",
        "Effect semantics are not opening-hand mulligan keeps.",
        "Darkbishop Benedictus / `SW_448` hero-power-transform semantics, but do not emit a Mulligan keep without explicit opening-hand source text.",
        "`<current-revision>/configure_summary.json.config_proof_summary` and `<current-revision>/configure_summary.json.config_quality_summary` only as diagnostic proof.",
        "Card-intent taxonomy is diagnostic-only.",
        "Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning.",
    ]

    for phrase in required_entrypoint_phrases:
        assert phrase in text


def test_hsconfig_detailed_policy_lives_in_references_not_entrypoint() -> None:
    skill = _skill_text()
    references = _active_reference_text()

    detailed_reference_phrases = [
        "source claim -> normalized `claim_kind` -> semantic qualifiers",
        "source_closure_intake_receipt.json",
        "latest_research_result_contract_first_non_promoting_*",
        "mechanic lowering registry",
        "warning_boundaries",
        "globalvalue_numeric_tuning",
        "per_card_config_readiness_report.json",
    ]

    for phrase in detailed_reference_phrases:
        assert phrase in references

    for phrase in [
        "### Claim Lifecycle End States",
        "## Package Preparation",
        "## Fixture Stage Semantics",
        "## Diagnostic And Expert Paths",
    ]:
        assert phrase not in skill


def test_hsconfig_skill_entrypoint_does_not_create_forbidden_scope() -> None:
    text = _skill_text().lower()
    forbidden_phrases = [
        "runtime logs to tune",
        "hdt parsing",
        "winrate validation",
        "candidate promotion",
        "post-run tuning",
        "source status blocks apply",
        "source_closure_receipt applies runtime",
        "source_closure_receipt blocks apply",
        "source_autopilot_report.json remains the normal apply authority",
        "presume.json is normal output",
        "concede.json is normal output",
        "cardbehavior.json is normal output",
    ]

    for phrase in forbidden_phrases:
        assert phrase not in text
